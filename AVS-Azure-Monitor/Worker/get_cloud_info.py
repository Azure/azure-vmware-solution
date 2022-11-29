import sys
import os
from azure.mgmt.avs import AVSClient
from azure.identity import DefaultAzureCredential
from azure.identity import ChainedTokenCredential,ManagedIdentityCredential

try:
    MSI_credential = ManagedIdentityCredential(client_id=os.environ['client_id'])
except:
    MSI_credential = DefaultAzureCredential()
credential = ChainedTokenCredential(MSI_credential)
resource_id = os.environ['AVS_CLOUD_ID']
subscription_id = resource_id[15:resource_id[15:].find("/")+15]
avs_client = AVSClient(credential, subscription_id)
resource_group_name = resource_id[resource_id.find("resourceGroups/")+15:resource_id.find("/",resource_id.find("resourceGroups/")+15)]
private_cloud_name = resource_id[resource_id.find("privateClouds/")+14:]
#get cloud object
cloud = avs_client.private_clouds.get(resource_group_name=resource_group_name,private_cloud_name=private_cloud_name)
#colllect more info
region_id = cloud.location
cloud_credentials = avs_client.private_clouds.list_admin_credentials(resource_group_name, cloud.name)
if (sys.argv[1] == "user"):
    print(cloud_credentials.vcenter_username)
if (sys.argv[1] == "pass"):
    print(cloud_credentials.vcenter_password)
if (sys.argv[1] == "ip"):
    print(cloud.endpoints.vcsa)
if (sys.argv[1] == "region"):
    print(region_id)
