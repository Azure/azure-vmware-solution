// =============================================================================
//  AVS AI Data Agent - reusable deployment
// =============================================================================
//  Provisions the Azure infrastructure that lets a managed Azure AI Foundry
//  agent query PRIVATE databases running on VMs inside your AVS private cloud:
//
//    - A delegated Container Apps subnet in YOUR existing VNet
//    - Azure Container Registry (holds the MCP server image)
//    - Key Vault (+ the read-only DB secret) with RBAC
//    - A VNet-integrated Container Apps environment + the MCP server app
//    - Managed-identity role assignments (Key Vault Secrets User, AcrPull)
//    - (optional) an Azure AI Foundry (AIServices) account + a model deployment
//
//  PREREQUISITES (you already have these if you run AVS):
//    - An AVS private cloud with your databases on a workload segment
//    - A VNet that can route to that AVS private cloud. On Gen 1 that is a VNet with
//      ExpressRoute connectivity; on Gen 2 it is the VNet the private cloud is
//      deployed into (or one peered to it). This template is the same either way --
//      it never references an AVS resource, only the VNet you name below.
//
//  DEPLOY:
//    az deployment group create -g <your-rg> --template-file main.bicep \
//      --parameters existingVnetName=<your-vnet> acaSubnetPrefix=10.40.8.0/23 \
//                   sqlPassword=<read-only-db-password>
//
//  AFTER DEPLOY (the parts ARM can't do):
//    1. Update sources.yaml with your DB endpoints, then build + push the image:
//         az acr build --registry <acrName output> --image avs-mcp:v1 .
//    2. Point the app at your image:
//         az containerapp update -n <namePrefix>-mcp-server -g <rg> \
//           --image <acrLoginServer output>/avs-mcp:v1
//    3. Create a read-only login (e.g. agentreader) on each database.
//    4. In the Azure AI Foundry portal: create a project + agent (use the model
//       deployed here), and attach the MCP tool:
//         URL   = https://<mcpFqdn output>/mcp
//         Auth  = Microsoft Entra / Project Managed Identity
//         Audience = api://<your MCP app registration>
//    5. Lock the endpoint to your agent by setting these app env vars:
//         ALLOWED_AUDIENCES = api://<your app registration>
//         ALLOWED_CALLERS   = <the Foundry project managed-identity app id (azp)>
// =============================================================================

@description('Location for all resources.')
param location string = resourceGroup().location

@description('Short prefix used to name the resources.')
param namePrefix string = 'avsai'

@description('Name of the EXISTING VNet that can route to your AVS private cloud (Gen 1: a VNet with ExpressRoute connectivity; Gen 2: the private cloud\'s own VNet, or one peered to it).')
param existingVnetName string

@description('Name of the delegated subnet to create for Container Apps.')
param acaSubnetName string = 'aca-subnet'

@description('Create the delegated Container Apps subnet. Set to FALSE when you already created it with connectivity.bicep, which also creates a subnet named "aca-subnet" -- otherwise this template re-writes that subnet and a mismatched acaSubnetPrefix will silently reconfigure or fail it.')
param createAcaSubnet bool = true

@description('Address prefix for the delegated Container Apps subnet (must fit inside the existing VNet and be at least /23).')
param acaSubnetPrefix string = '10.40.8.0/23'

@description('Read-only SQL login the agent uses to query your databases.')
param sqlUser string = 'agentreader'

@description('Password for the read-only SQL login. Stored as a Key Vault secret.')
@secure()
param sqlPassword string

@description('Container image for the MCP server. Defaults to a public placeholder; swap to your ACR image after you build + push it.')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Microsoft Entra tenant ID used for in-app token validation.')
param tenantId string = subscription().tenantId

@description('Allowed audiences (comma-separated) for in-app token validation. Set to your MCP app-registration audience.')
param allowedAudiences string = ''

@description('Allowed caller app IDs / azp (comma-separated). Set to your Foundry project managed identity after the agent exists.')
param allowedCallers string = ''

@description('Also deploy an Azure AI Foundry (AIServices) account + project + model deployment.')
param deployFoundry bool = true

@description('Name of the Foundry project that will host the agent. Its managed identity is the caller you put in allowedCallers.')
param foundryProjectName string = '${namePrefix}-project'

@description('Location for the Foundry account. Defaults to the main location, but the agent reaches the MCP server over public HTTPS, so Foundry can live in a model-rich region when the AVS region has no GPT models (e.g. westus2).')
param foundryLocation string = location

@description('Model to deploy in Foundry (only used when deployFoundry = true). Model availability AND lifecycle vary by region: a model in a "Deprecating" state is rejected for new deployments. Check `az cognitiveservices model list -l <foundryLocation>` before deploying.')
param modelName string = 'gpt-5.4-mini'

@description('Version of the model to deploy.')
param modelVersion string = '2026-03-17'

@description('Temporarily allow any validly-authenticated Entra caller so you can read the caller azp from the logs and then populate allowedCallers. Never leave this on: it disables the caller allow-list (it does NOT disable token validation).')
param discoveryMode bool = false

// ---- names -----------------------------------------------------------------
// Key Vault names are GLOBALLY unique across all of Azure, so a bare '<prefix>-kv'
// collides with other tenants' vaults (and soft-delete keeps deleted names reserved).
// 24 chars is the hard limit.
var kvName = take('${namePrefix}-kv-${uniqueString(resourceGroup().id)}', 24)
var acrName = '${namePrefix}acr${uniqueString(resourceGroup().id)}'
var envName = '${namePrefix}-mcp-env'
var appName = '${namePrefix}-mcp-server'
// The Foundry account's customSubDomainName becomes a GLOBAL DNS label
// (<name>.services.ai.azure.com), so it needs the same uniqueness treatment as the
// vault and the registry -- a bare '<prefix>-foundry' is claimable only once.
var foundryName = '${namePrefix}-foundry-${uniqueString(resourceGroup().id)}'
var secretName = 'sql-agentreader-password'

// built-in role definition IDs
var kvSecretsUserRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6') // Key Vault Secrets User
var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')       // AcrPull

// ---- existing VNet + new delegated subnet ----------------------------------
resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' existing = {
  name: existingVnetName
}

resource acaSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-11-01' = if (createAcaSubnet) {
  parent: vnet
  name: acaSubnetName
  properties: {
    addressPrefix: acaSubnetPrefix
    delegations: [
      {
        name: 'aca-delegation'
        properties: {
          serviceName: 'Microsoft.App/environments'
        }
      }
    ]
  }
}

// Resolve the subnet id either way. A conditional resource's .id is still valid to
// reference, but reading it when the condition is false yields a placeholder, so
// build the id from the parent instead.
var acaSubnetId = '${vnet.id}/subnets/${acaSubnetName}'

// ---- User-assigned identity -------------------------------------------------
// Created up front so AcrPull / Key Vault roles can be granted BEFORE the app starts.
// A system-assigned identity cannot work here: the app needs AcrPull to pull its image,
// but the role assignment would depend on the app's own principalId -- a deadlock that
// leaves the app stuck in InProgress forever.
resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-mcp-identity'
  location: location
}

// ---- Azure Container Registry -----------------------------------------------
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

// ---- Key Vault (RBAC) + read-only DB secret --------------------------------
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  properties: {
    tenantId: tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
  }
}

resource sqlSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: secretName
  properties: {
    value: sqlPassword
  }
}

// ---- Container Apps environment (VNet-integrated) --------------------------
// ---- Log Analytics ----------------------------------------------------------
// Without a log destination the container's stdout is discarded: crashes are
// undiagnosable AND the documented "read the caller azp from the logs" discovery
// workflow is impossible, because that azp line is printed to stdout.
resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${namePrefix}-logs'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// The infrastructure subnet is delegated to Microsoft.App/environments, which requires a
// workload-profiles environment. A Consumption-only (V1) environment rejects delegated subnets.
resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  // Referencing acaSubnetId as a string loses the implicit dependency, so declare it.
  dependsOn: [
    acaSubnet
  ]
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: law.properties.customerId
        sharedKey: law.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: acaSubnetId
      internal: false
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

// ---- MCP server Container App ----------------------------------------------
resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${uami.id}': {}
    }
  }
  dependsOn: [
    acrRoleAssignment
    kvRoleAssignment
  ]
  properties: {
    managedEnvironmentId: env.id
    // Must match a profile defined on the environment, otherwise the app never schedules.
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: uami.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'mcp'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'KEY_VAULT_URL', value: kv.properties.vaultUri }
            { name: 'SQL_USER', value: sqlUser }
            { name: 'HOST', value: '0.0.0.0' }
            { name: 'PORT', value: '8000' }
            { name: 'TENANT_ID', value: tenantId }
            { name: 'ALLOWED_AUDIENCES', value: allowedAudiences }
            { name: 'ALLOWED_CALLERS', value: allowedCallers }
            { name: 'DISCOVERY_MODE', value: string(discoveryMode) }
            // Tells DefaultAzureCredential which identity to use for Key Vault.
            { name: 'AZURE_CLIENT_ID', value: uami.properties.clientId }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
      }
    }
  }
}

// ---- RBAC: app managed identity -> Key Vault Secrets User + AcrPull ---------
// Scoped to the user-assigned identity so both roles exist before the app is created.
resource kvRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, uami.id, kvSecretsUserRoleId)
  scope: kv
  properties: {
    roleDefinitionId: kvSecretsUserRoleId
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource acrRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, uami.id, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---- (optional) Azure AI Foundry account + project + model deployment ------
// allowProjectManagement is REQUIRED for the Agent Service: without it the account
// cannot host a project, and the project's managed identity is what authenticates to
// the MCP server. An account created without it can only serve raw model inference.
resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = if (deployFoundry) {
  name: foundryName
  location: foundryLocation
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: toLower(foundryName)
    publicNetworkAccess: 'Enabled'
  }
}

// The project owns the managed identity that calls the MCP server. Its app id (azp)
// is what you put in allowedCallers.
resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = if (deployFoundry) {
  parent: foundry
  name: foundryProjectName
  location: foundryLocation
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: foundryProjectName
    description: 'Agents that query private databases inside AVS via the MCP server.'
  }
}

resource model 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = if (deployFoundry) {
  parent: foundry
  name: modelName
  sku: {
    name: 'GlobalStandard'
    capacity: 50
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
  }
}

// ---- outputs ----------------------------------------------------------------
output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
output mcpFqdn string = app.properties.configuration.ingress.fqdn
output mcpEndpoint string = 'https://${app.properties.configuration.ingress.fqdn}/mcp'
output keyVaultUri string = kv.properties.vaultUri
output keyVaultName string = kv.name
output appPrincipalId string = uami.properties.principalId
output appClientId string = uami.properties.clientId
output foundryEndpoint string = deployFoundry ? foundry!.properties.endpoint : ''
// Data-plane endpoint the Agent Service SDK / REST API talks to.
output foundryProjectEndpoint string = deployFoundry ? 'https://${toLower(foundryName)}.services.ai.azure.com/api/projects/${foundryProjectName}' : ''
// Control-plane ID of the Foundry account -- the {armId} used when creating a project connection.
output foundryAccountId string = deployFoundry ? foundry!.id : ''
// Object (principal) ID of the project's system-assigned identity -- use it for role
// assignments. NOTE: this is NOT the `azp` your MCP server sees. `azp` is the calling
// application's *client* ID; read the real value from the discovery log line.
output foundryProjectPrincipalId string = deployFoundry ? foundryProject!.identity.principalId : ''
