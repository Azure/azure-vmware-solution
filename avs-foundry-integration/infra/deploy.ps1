#Requires -Version 7
<#
.SYNOPSIS
  Deploys the AVS AI Data Agent infrastructure, then (optionally) builds + pushes the
  MCP server image and points the Container App at it.

.DESCRIPTION
  Runs main.bicep in the given resource group, captures the outputs, builds the MCP
  image into the created ACR from your app source folder, and updates the Container App.
  The Foundry agent + MCP-tool wiring is a one-time portal (data-plane) step, printed at the end.

.EXAMPLE
  ./deploy.ps1 -ResourceGroup avs-ai-rg -ExistingVnetName my-vnet -Location westus2 `
               -FoundryLocation eastus2 -SkipAcaSubnet `
               -SqlPassword (Read-Host 'DB password' -AsSecureString) `
               -AppSourcePath ../app
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]   $ResourceGroup,
    [Parameter(Mandatory)][string]   $ExistingVnetName,
    # Defaults to the resource group's location. Set this when the RG lives in a
    # different region than your VNet/AVS private cloud -- ARM would otherwise place
    # the Container Apps environment away from the VNet it has to join.
    [string]                         $Location,
    # Foundry is reached over public HTTPS, so it can sit in a model-rich region when
    # the AVS region has no GPT models (e.g. westus2). Defaults to -Location.
    [string]                         $FoundryLocation,
    [string]                         $AcaSubnetPrefix = '10.40.8.0/23',
    [string]                         $NamePrefix      = 'avsai',
    [Parameter(Mandatory)][securestring] $SqlPassword,
    [string]                         $AppSourcePath   = 'app',    # folder with Dockerfile, mcp_server.py, sources.yaml (bundled)
    [string]                         $ImageTag        = 'avs-mcp:v1',
    # Set when connectivity.bicep already created the delegated 'aca-subnet'.
    [switch]                         $SkipAcaSubnet,
    # Temporarily accept any valid Entra token so you can read the caller azp from the
    # logs and populate ALLOWED_CALLERS. Never leave this on.
    [switch]                         $DiscoveryMode,
    [switch]                         $SkipImageBuild
)

$ErrorActionPreference = 'Stop'

# Container Apps workload profiles need a recent CLI. Older builds pin the Microsoft.App
# API to 2022-10-01, which predates workload profiles: `az containerapp update` fails with
# WorkloadProfilePropertyNotSupportedInApiVersion, and `az containerapp show` reports
# workloadProfiles as null even when they are set -- badly misleading during triage.
$minAzVersion = [version]'2.53.0'
$azVer = (az version --output json | ConvertFrom-Json).'azure-cli'
if ([version]$azVer -lt $minAzVersion) {
    throw "azure-cli $azVer is too old for Container Apps workload profiles. Upgrade to >= $minAzVersion (az upgrade)."
}

$here     = Split-Path -Parent $PSCommandPath
$template = Join-Path $here 'main.bicep'
if (-not [System.IO.Path]::IsPathRooted($AppSourcePath)) { $AppSourcePath = Join-Path (Split-Path -Parent $here) $AppSourcePath }
$pwdPlain = [System.Net.NetworkCredential]::new('', $SqlPassword).Password

if (-not $Location) {
    $Location = az group show --name $ResourceGroup --query location -o tsv
    Write-Host "    (no -Location given; using the resource group's region: $Location)" -ForegroundColor DarkGray
}
if (-not $FoundryLocation) { $FoundryLocation = $Location }

Write-Host '==> Deploying infrastructure (subnet, ACR, Key Vault, Container Apps, Foundry)...' -ForegroundColor Cyan
$deployName = "avs-ai-agent-$((Get-Date).ToString('yyyyMMddHHmmss'))"
$outJson = az deployment group create `
    --name $deployName `
    --resource-group $ResourceGroup `
    --template-file $template `
    --parameters existingVnetName=$ExistingVnetName acaSubnetPrefix=$AcaSubnetPrefix namePrefix=$NamePrefix `
                 sqlPassword=$pwdPlain location=$Location foundryLocation=$FoundryLocation `
                 createAcaSubnet=$((-not $SkipAcaSubnet).ToString().ToLower()) `
                 discoveryMode=$($DiscoveryMode.IsPresent.ToString().ToLower()) `
    --query properties.outputs -o json
if ($LASTEXITCODE -ne 0) { throw 'Deployment failed.' }
$out = $outJson | ConvertFrom-Json

$acrName         = $out.acrName.value
$acrLoginServer  = $out.acrLoginServer.value
$mcpEndpoint     = $out.mcpEndpoint.value
$foundryEndpoint = $out.foundryEndpoint.value
$projectEndpoint = $out.foundryProjectEndpoint.value
$foundryAccountId = $out.foundryAccountId.value
$keyVaultName    = $out.keyVaultName.value
$appName         = "$NamePrefix-mcp-server"

Write-Host "    ACR:          $acrName"     -ForegroundColor Green
Write-Host "    MCP endpoint: $mcpEndpoint" -ForegroundColor Green

if (-not $SkipImageBuild) {
    if (-not (Test-Path (Join-Path $AppSourcePath 'Dockerfile'))) {
        Write-Warning "No Dockerfile in '$AppSourcePath'. It should contain Dockerfile, mcp_server.py and sources.yaml (with YOUR database endpoints). Build manually, then run: az containerapp update -n $appName -g $ResourceGroup --image $acrLoginServer/$ImageTag"
    }
    else {
        Write-Host "==> Building + pushing $ImageTag from $AppSourcePath ..." -ForegroundColor Cyan
        # On Windows, `az acr build` streams logs through colorama and dies with
        # UnicodeEncodeError (cp1252) even though the SERVER-SIDE build succeeded.
        # Force UTF-8 and, if the client still fails, confirm the real outcome from the
        # registry instead of aborting a successful build.
        $prevEnc = $env:PYTHONIOENCODING
        $env:PYTHONIOENCODING = 'utf-8'
        try { az acr build --registry $acrName --image $ImageTag $AppSourcePath }
        finally { $env:PYTHONIOENCODING = $prevEnc }

        if ($LASTEXITCODE -ne 0) {
            $tag = $ImageTag.Split(':')[-1]
            $repo = $ImageTag.Split(':')[0]
            $tags = az acr repository show-tags --name $acrName --repository $repo -o tsv 2>$null
            if ($tags -contains $tag) {
                Write-Warning "az acr build reported a client-side failure, but $ImageTag exists in $acrName - treating the build as successful (known Windows log-streaming bug)."
            }
            else { throw 'Image build failed.' }
        }

        Write-Host '==> Pointing the Container App at your image...' -ForegroundColor Cyan
        az containerapp update --name $appName --resource-group $ResourceGroup --image "$acrLoginServer/$ImageTag" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to point $appName at $acrLoginServer/$ImageTag. The app is still running the placeholder image." }
    }
}

Write-Host ''
Write-Host 'Infrastructure ready.' -ForegroundColor Green
Write-Host "  MCP endpoint     : $mcpEndpoint"
Write-Host "  Foundry account  : $foundryEndpoint"
Write-Host "  Key Vault        : $keyVaultName"
Write-Host "  {project}        : $projectEndpoint"
Write-Host "  {armId}          : $foundryAccountId"
Write-Host "  ARM deployment   : $deployName  (az deployment group show -g $ResourceGroup -n $deployName --query properties.outputs)"
Write-Host ''
Write-Host ''
Write-Host 'NEXT STEPS (one-time, data plane) - see README.md:' -ForegroundColor Yellow
Write-Host '  4. Create the read-only DB login on each database (matching -SqlPassword).'
Write-Host '  5. Create an Entra app registration to act as the token audience.'
Write-Host "  6. Create the agent + an MCP tool pointing at: $mcpEndpoint"
Write-Host '     (the Foundry project and model were created for you by the template).'
Write-Host '     You need the Foundry User role on the project to create and run agents.'
Write-Host '  7. Ask one question, then read the caller identity and lock the endpoint down:'
Write-Host "       az containerapp logs show -n $appName -g $ResourceGroup --type console --tail 40 | Select-String AUTH"
Write-Host "       az containerapp update -n $appName -g $ResourceGroup ``"
Write-Host '         --set-env-vars ALLOWED_AUDIENCES=api://<appId>,<appId> ALLOWED_CALLERS=<azp-from-the-AUTH-discovery-log-line> DISCOVERY_MODE=false'
if (-not $DiscoveryMode) {
    Write-Host ''
    Write-Warning "Deployed WITHOUT -DiscoveryMode, so /mcp fails closed (503) until ALLOWED_CALLERS is set. To learn the agent's azp first, redeploy with -DiscoveryMode or set DISCOVERY_MODE=true on the app."
}
