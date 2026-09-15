using './main.bicep'

// ---------------------------------------------------------------------------
//  Fill these in, then deploy with:
//    az deployment group create -g <your-rg> \
//      --parameters main.bicepparam --parameters sqlPassword=<db-password>
//  (pass sqlPassword on the command line so the secret isn't stored in the file)
// ---------------------------------------------------------------------------

// --- Required ---
param existingVnetName = 'REPLACE-with-your-vnet'   // VNet with ExpressRoute to your AVS private cloud
param acaSubnetPrefix  = '10.40.8.0/23'             // a free /23 inside that VNet for the bridge
param createAcaSubnet  = true                       // false if connectivity.bicep already made 'aca-subnet'

// --- Secret: override at deploy time; do NOT commit a real value ---
param sqlPassword = 'REPLACE-at-deploy-time'

// --- Naming / options ---
param namePrefix     = 'avsai'
param sqlUser        = 'agentreader'
param containerImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest' // swap after az acr build

// --- Azure AI Foundry (optional) ---
param deployFoundry = true
// Foundry is reached over public HTTPS, so it can sit in a model-rich region even when
// your AVS region has none (e.g. westus2). Leave commented to follow `location`.
// param foundryLocation = 'eastus2'
// VERIFY BEFORE DEPLOYING - model availability AND lifecycle are per-region, and a
// "Deprecating" model is refused for new deployments:
//   az cognitiveservices model list -l <region> -o table
param modelName     = 'gpt-5.4-mini'
param modelVersion  = '2026-03-17'

// --- Fill in AFTER the Foundry agent exists (locks the endpoint to your agent) ---
param allowedAudiences = ''   // e.g. api://<your-mcp-app-registration>
param allowedCallers   = ''   // the Foundry project managed-identity app id (azp claim)

// Leave false. Set true for ONE deployment to read the caller azp from the container
// logs, then set allowedCallers and turn it back off. It does not disable token
// validation, but it does disable the caller allow-list on an internet-facing ingress.
param discoveryMode = false
