# Title: Azure VMware Solution Private Cloud Cluster Auto-scale Scale-In PowerShell Runbook

# Purpose: Azure Automation PowerShell Runbook for the scale-in of an Azure VMware Solution management or resource cluster.

[OutputType("PSAzureOperationResponse")]
param (
    [Parameter (Mandatory=$false)]
    [object] $WebhookData
)
$ErrorActionPreference = "stop"

# Minimum number of nodes in allowed to scale up to in the cluster
# This is set to 5 for the purpose of this example. The minimum number of nodes in a cluster is 3.
$minnodes = 5

# Array of datastore names in storage alert used to map to clustername
$vsandatastorename = 'vsanDatastore (1)','vsanDatastore (2)','vsanDatastore (3)','vsanDatastore (4)','vsanDatastore (5)','vsanDatastore (6)','vsanDatastore (7)','vsanDatastore (8)','vsanDatastore (9)','vsanDatastore (10)','vsanDatastore (11)'

if ($WebhookData) {
  # Get the data object from WebhookData
  $WebhookBody = (ConvertFrom-Json -InputObject $WebhookData.RequestBody)

  # Get the info needed to identify the AVS Private Cloud (AVS alerts use "azureMonitorCommonAlertSchema")
  $schemaId = $WebhookBody.schemaId
  Write-Verbose "schemaId: $schemaId" -Verbose
  if ($schemaId -eq "azureMonitorCommonAlertSchema") {
    # This is the common Metric Alert schema (released March 2019)
    $Essentials = [object] ($WebhookBody.data).essentials
    # Get the first target only as this script doesn't handle multiple

    $alertTargetIdArray = (($Essentials.alertTargetIds)[0]).Split("/")
    $SubId = ($alertTargetIdArray)[2]
    $ResourceGroupName = ($alertTargetIdArray)[4]
    $ResourceType = ($alertTargetIdArray)[6] + "/" + ($alertTargetIdArray)[7]
    $ResourceName = ($alertTargetIdArray)[-1]
    $status = $Essentials.monitorCondition
    $alertContext = [object] ($WebhookBody.data).alertContext
    $alertContextdimensionsName = $alertContext.condition.allOf[0].dimensions[0].name
    $alertContextdimensionsValue = $alertContext.condition.allOf[0].dimensions[0].value
    Write-Verbose "*** alertContextdimensionsName: $alertContextdimensionsName" -Verbose
    Write-Verbose "*** alertContextdimensionsValue: $alertContextdimensionsValue" -Verbose
  }
  else {
    # Schema not supported
    Write-Error "The alert data schema - $schemaId - is not supported."
  }
  Write-Verbose "*** status: $status" -Verbose
  if (($status -eq "Activated") -or ($status -eq "Fired")) {
    Write-Verbose "*** resourceType: $ResourceType" -Verbose
    Write-Verbose "*** resourceName: $ResourceName" -Verbose
    Write-Verbose "*** resourceGroupName: $ResourceGroupName" -Verbose
    Write-Verbose "*** subscriptionId: $SubId" -Verbose

    # Determine code path depending on the resourceType
    if ($ResourceType -eq "Microsoft.AVS/privateClouds")
    {
      # This is an AVS Private Cloud
      Write-Verbose "*** This is an AVS Private Cloud." -Verbose

      # Authenticate to Azure with service principal and certificate and set subscription
      Write-Verbose "*** Authenticating to Azure" -Verbose
      Connect-AzAccount -Identity -ErrorAction Stop
      Write-Verbose "Authentication successful."
      Write-Verbose "Setting subscription context to $SubId"
      Set-AzContext -SubscriptionId $SubId -ErrorAction Stop | Write-Verbose

      # Part 1 - Detect if Cluster Type is the Management Cluster (Cluster-1) or a Resource cluster (Cluster-2 -> Cluster-12)
      # Part 2 - Detect if the alert type is storage, cpu or ram and map to correct cluster name
      # This is necessary because the AVS management and resource clusters use different PowerShell commands (Get-AzVMwarePrivateCloud, Update-AzVMwarePrivateCloud, Get-AzVMwareCluster, Update-AzVMwareCluster)
      if (($alertContextdimensionsValue -eq "Cluster-1") -or ($alertContextdimensionsValue -eq "vsanDatastore")) {
        # Management Cluster (Cluster-1) detected
        $ClusterTypeManagement = $true
		$ClusterName = "Cluster-1"
        Write-Verbose "*** Management ($ClusterName) detected" -Verbose
      }
      else {
        # Resource Cluster (Cluster-2 -> Cluster-12) detected
        $ClusterTypeManagement = $false
        Write-Verbose "*** Resource Cluster (Cluster-2 -> Cluster-12) detected" -Verbose
        if ($alertContextdimensionsName -eq "clustername") {
          # CPU or RAM alert detected, use existing $alertContextdimensionsValue, which has the correct clustername (Cluster-2 -> Cluster-12)
		  $ClusterName = $alertContextdimensionsValue
          Write-Verbose "*** CPU or RAM Alert detected" -Verbose
		}
        else {
          # Storage alert detected, search through array for datastore name (vsanDatastore (1) -> vsanDatastore (11)) and map to clustername (Cluster-2 -> Cluster-12)
          for ($arrayindex = 0; $arrayindex -lt $vsandatastorename.count; $arrayindex++) {
            if ($alertContextdimensionsValue -eq $vsandatastorename[$arrayindex]) {
              $ClusterName = "Cluster-$($arrayindex+2)"
              Write-Verbose "*** Storage Alert detected" -Verbose
			  Write-Verbose "*** alertContextdimensionsValue: $alertContextdimensionsValue" -Verbose
            }
          }
        }
      }
      Write-Verbose "*** ClusterTypeManagement: $ClusterTypeManagement" -Verbose
      Write-Verbose "*** ClusterName: $ClusterName" -Verbose

      # Get Private Cloud (includes Management Cluster: Cluster-1) Object
      $MgmtCluster = Get-AzVMwarePrivateCloud -SubscriptionId $SubId -ResourceGroupName $ResourceGroupName -Name $ResourceName			

      # Get Private Cloud Provisioning State
      $PrivateCloudProvisioningState = $MgmtCluster.ProvisioningState

      # Check Private Cloud Provisioning State
      if ($PrivateCloudProvisioningState -eq "Succeeded") {

        # Cluster Size calculation for Standard or Stretched Cluster
        # We deliberately rely upon the Azure VMware Solution management & control plane to enforce the cluster size minimum (standard 3 nodes, stretched 6 nodes) and the cluster size maximum (16 nodes). This provides operational simplicity in maintaining this PS Runbook.

        # Get Availability Strategy (SingleZone or DualZone)
        $MgmtClusterAvailabilityType = $MgmtCluster.AvailabilityStrategy
        Write-Verbose "*** MgmtClusterAvailabilityType: $MgmtClusterAvailabilityType" -Verbose

        # Cluster Type Check, Cluster Size Calculation and Cluster Autoscale Execution
        if ($ClusterTypeManagement -eq $true) {
          # Management Cluster Size Calculation & Execution
          $MgmtClusterCurrentSize = $MgmtCluster.ManagementClusterSize

          # Check if the current size is less than or equal to the minimum nodes allowed
          # If so, exit the script and do not attempt to scale in the cluster
          if ($MgmtClusterCurrentSize -le $minnodes) {
            Write-Verbose "*** Management Cluster already at or below min size $minnodes. No action taken." -Verbose
            return
          }

          if ($MgmtClusterAvailabilityType -eq "DualZone") {
            # DualZone requires 1 node per Availability Zone = 2
            $MgmtClusterNewSize = $MgmtClusterCurrentSize - 2
          }
          elseif ($MgmtClusterAvailabilityType -eq "SingleZone") {
            # SingleZone requires 1 node per Availability Zone = 1
            $MgmtClusterNewSize = $MgmtClusterCurrentSize - 1
          }
          else {
            # Unknown Availability Strategy Type
            Write-Error "The Azure VMware Solution Availability Strategy - $MgmtClusterAvailabilityType - is not supported."
          }
          Write-Verbose "*** MgmtClusterNewSize: $MgmtClusterNewSize" -Verbose
          # Execute Management Cluster Autoscale Command
          Write-Verbose "*** Scaling PrivateCloudName: $ResourceName Management Cluster (Cluster-1) from $MgmtClusterCurrentSize nodes to $MgmtClusterNewSize nodes" -Verbose
          Write-Verbose "*** PrivateCloudName: $ResourceName resides in resourceGroupName: $ResourceGroupName & subscriptionId: $SubId" -Verbose
          Update-AzVMwarePrivateCloud -SubscriptionId $SubId -ResourceGroupName $ResourceGroupName -Name $ResourceName -ManagementClusterSize $MgmtClusterNewSize  
        }
        else {
          # Resource Cluster Size Calculation & Execution
          $ResourceCluster = Get-AzVMwareCluster -SubscriptionId $SubId -ResourceGroupName $ResourceGroupName -PrivateCloudName $ResourceName -Name $ClusterName
          $ResourceClusterCurrentSize = $ResourceCluster.Size

          # Check if the current size is less than or equal to the minimum nodes allowed
          # If so, exit the script and do not attempt to scale in the cluster
          if ($ResourceClusterCurrentSize -le $minnodes) {
            Write-Verbose "*** Resource Cluster already at or below min size $minnodes. No action taken." -Verbose
            return
          }

          if ($MgmtClusterAvailabilityType -eq "DualZone") {
            # DualZone requires 1 node per Availability Zone = 2
            $ResourceClusterNewSize = $ResourceClusterCurrentSize - 2
          }
          elseif ($MgmtClusterAvailabilityType -eq "SingleZone") {
            # SingleZone requires 1 node per Availability Zone = 1
            $ResourceClusterNewSize = $ResourceClusterCurrentSize - 1
          }
          else {
            # Unknown Availability Strategy Type
            Write-Error "The Azure VMware Solution Availability Strategy - $MgmtClusterAvailabilityType - is not supported."
          }
          Write-Verbose "*** ResourceClusterNewSize: $ResourceClusterNewSize" -Verbose
          # Execute Resource Cluster Autoscale Command
          Write-Verbose "*** Scaling PrivateCloudName: $ResourceName Resource Cluster $ClusterName from $ResourceClusterCurrentSize nodes to $ResourceClusterNewSize nodes" -Verbose
          Write-Verbose "*** PrivateCloudName: $ResourceName resides in resourceGroupName: $ResourceGroupName & subscriptionId: $SubId" -Verbose
          Update-AzVMwareCluster -SubscriptionId $SubId -ResourceGroupName $ResourceGroupName -PrivateCloudName $ResourceName -Name $ClusterName -ClusterSize $ResourceClusterNewSize
        }
      }
      else {
        # SDDC Provisioning State is not Succeeded
        Write-Error "The Azure VMware Solution Private Cloud: $ResourceName provisioning state: $PrivateCloudProvisioningState is not in Succeeded state."
      }
      # [OutputType(PSAzureOperationResponse")]
    }
    else {
      # ResourceType not supported
      Write-Error "$ResourceType is not a supported resource type for this runbook."
    }
  }
  else {
    # The alert status was not 'Activated' or 'Fired' so no action taken
    Write-Verbose ("*** No action taken. Alert status: " + $status) -Verbose
  }
}
else {
  # Error
  Write-Error "This runbook is meant to be started from an Azure alert webhook only."
}
