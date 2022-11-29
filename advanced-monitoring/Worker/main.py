from urllib import request
import requests
import json
import datetime
import pandas
from time import sleep
import urllib3
import os
import os.path
from azure.mgmt.avs import AVSClient
from azure.identity import DefaultAzureCredential
from azure.identity import ChainedTokenCredential,ManagedIdentityCredential
from azure.identity import AzureCliCredential
import logging

pid = "/tmp/nsx-stats.pid"
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.propagate = False
fh = logging.FileHandler("/var/log/nsx-stats.log", "w")
fh.setLevel(logging.DEBUG)
logger.addHandler(fh)
keep_fds = [fh.stream.fileno()]

class NSXTConnection:
    def __init__(self, nsxtUri,nsxtUsername, nsxtPassword):
        self.nsxtUri = nsxtUri
        self.nsxtUsername = nsxtUsername
        self.nsxtPassword = nsxtPassword
        self.nsxtPolicyUri = nsxtUri+ "/policy/api/v1"

class NSXTTier0Interface:
    def __init__(self, path, edge_path,T0):
        self.path = path
        self.edge_path = edge_path
        self.name = path[path.rfind("/")+1:]
        self.NSXTier0 = T0
        self.connection= T0.connection
    def getInterfaceStats(self):
        return _getInterfaceStats(self)

class NSXTTier0:
    def __init__(self, path, name, connection):
        self.path = path
        self.name = name
        self.connection = connection
        self.local_services = _getT0LocaleServices(self.connection,self.path)
        self.interfaces = _getT0Interfaces(self)
    def getInterfacesStats(self):
        interfaceStats = []
        for interface in self.interfaces:
            interfaceStats.append(interface.getInterfaceStats())
        return pandas.concat(interfaceStats)

class NSXEdgeNode:
    def __init__(self, id, display_name, connection):
        self.id = id
        self.display_name = display_name
        self.connection = connection
    def getCPUStats(self):
        nodecpu = json.loads(_getAPIResults(nsxtConnection=self.connection,uri= "/api/v1/transport-nodes/"+self.id+"/node/services/dataplane/cpu-stats",policy=False))
        df = pandas.json_normalize(nodecpu, record_path=['cores'])
        df.columns = df.columns.str.replace('/','_',regex=False)
        df['precise_timestamp'] = datetime.datetime.now(tz=datetime.timezone.utc)
        df['t0_name'] = self.display_name
        return df

def _getT0Interfaces(NSXTTier0):
    interfaces = []
    results = json.loads(_getAPIResults(nsxtConnection=NSXTTier0.connection,uri= NSXTTier0.local_services+"/interfaces"))
    for tier0interface in results['results']:
        interfaces.append(NSXTTier0Interface(path = tier0interface['path'], edge_path=tier0interface['edge_path'],T0= NSXTTier0))
    return interfaces

def _getT0(nsxtConnection, id):
    results = json.loads(_getAPIResults(nsxtConnection=nsxtConnection, uri="/infra/tier-0s/"+id))
    return NSXTTier0(path = results['path'], name = results['display_name'], connection=nsxtConnection)

def getT0s(nsxtConnection):
    T0s = []
    results = json.loads(_getAPIResults(nsxtConnection=nsxtConnection, uri="/infra/tier-0s"))
    for t0 in results['results']:
        T0s.append(_getT0(nsxtConnection=nsxtConnection, id=t0['display_name']))
    return T0s

def _getT0LocaleServices(nsxtConnection,path):
    tier0locales = json.loads(_getAPIResults(nsxtConnection=nsxtConnection, uri=path+"/locale-services"))
    return tier0locales['results'][0]['path']


def _getInterfaceStats(tier0interface):
    statsuri = tier0interface.path+"/statistics?enforcement_point_path=/infra/sites/default/enforcement-points/default&edge_path="+tier0interface.edge_path
    tier0interfacestats = json.loads(_getAPIResults(nsxtConnection=tier0interface.connection, uri=statsuri))
    df = pandas.json_normalize(tier0interfacestats, record_path=['per_node_statistics'])
    df.columns = df.columns.str.replace('.','_',regex=False)
    df['precise_timestamp'] = datetime.datetime.fromtimestamp(int(tier0interfacestats['per_node_statistics'][0]['last_update_timestamp'])/1000,tz=datetime.timezone.utc)
    df['t0_name'] = tier0interface.NSXTier0.name
    df['t0_interface'] = tier0interface.name
    return(df)

def getEdgeNodes(nsxtConnection):
    nodes = []
    results = json.loads(_getAPIResults(nsxtConnection=nsxtConnection, uri="/api/v1/transport-nodes?node_types=EdgeNode", policy=False))['results']
    for node in results:
        nodes.append(NSXEdgeNode(id = node['node_id'],display_name = node['display_name'], connection=nsxtConnection))
    return nodes

def getCpuStats(nodes):
    frames = []
    for node in nodes:
        frames.append(node.getCPUStats())
    return pandas.concat(frames)

def _getAPIResults(nsxtConnection, uri,json_body=None, policy = True):
    if (policy == True):
        r = requests.request(method="GET",url=nsxtConnection.nsxtPolicyUri+uri ,json=json_body,auth = requests.auth.HTTPBasicAuth (nsxtConnection.nsxtUsername, nsxtConnection.nsxtPassword), verify=False)
    else:
        r = requests.request(method="GET",url=nsxtConnection.nsxtUri+uri ,json=json_body,auth = requests.auth.HTTPBasicAuth (nsxtConnection.nsxtUsername, nsxtConnection.nsxtPassword), verify=False)
    if r.status_code == "200":
        return str(r.content).replace("\\n","")[2:-1]
    return r.content


def main():
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    #set output files:
    interface_csv = "./interface.csv"
    cpu_csv = "./cpu.csv"
    #Get Identity
    try:
        if os.environ['local'] == "True":
            credential = AzureCliCredential()
    except:
        try:
            MSI_credential = ManagedIdentityCredential(client_id=os.environ['client_id'])
        except:
            MSI_credential = DefaultAzureCredential()
        credential = ChainedTokenCredential(MSI_credential)
    #collect cloud info
    resource_id = os.environ['AVS_CLOUD_ID']
    subscription_id = resource_id[15:resource_id[15:].find("/")+15]
    avs_client = AVSClient(credential, subscription_id)
    resource_group_name = resource_id[resource_id.find("resourceGroups/")+15:resource_id.find("/",resource_id.find("resourceGroups/")+15)]
    private_cloud_name = resource_id[resource_id.find("privateClouds/")+14:]
    print("Subscription Id: {}\r\nResource Group Name: {}\r\nCloud Name: {}".format(subscription_id,resource_group_name,private_cloud_name))
    logger.debug("Subscription Id: {}\r\nResource Group Name: {}\r\nCloud Name: {}".format(subscription_id,resource_group_name,private_cloud_name))
    #get cloud object
    cloud = avs_client.private_clouds.get(resource_group_name=resource_group_name,private_cloud_name=private_cloud_name)
    #colllect more info
    region_id = cloud.location
    
    nsxUri= cloud.endpoints.nsxt_manager[:-1]
    cloud_credentials = avs_client.private_clouds.list_admin_credentials(resource_group_name, cloud.name)
     #set env for telegraf
    os.environ["VCSA_URI"] = cloud.endpoints.vcsa
    os.environ["VCSA_USER"] = cloud_credentials.vcenter_username
    os.environ["VCSA_PASS"] = cloud_credentials.vcenter_password
    os.environ["REGION"] = region_id
    os.system("systemctl stop telegraf")
    #set telegraf vars
    os.system('systemctl import-environment VCSA_URI')
    os.system('systemctl import-environment VCSA_USER')
    os.system('systemctl import-environment VCSA_PASS')
    os.system('systemctl import-environment REGION')
    os.system('systemctl import-environment AVS_CLOUD_ID')
    sleep(10)
    os.system("systemctl start telegraf")
    #connect to nsx-t
    nsxtConnection = NSXTConnection(nsxtUri=nsxUri, nsxtUsername=cloud_credentials.nsxt_username, nsxtPassword=cloud_credentials.nsxt_password)
    ### Get T0s Interfaces ###
    nsxtT0  = getT0s(nsxtConnection=nsxtConnection)[0]
    ### Get EVM Transport Nodes ###
    nodes = getEdgeNodes(nsxtConnection=nsxtConnection)
    count=0
    #main loop
    while True:
        try:
            # get stats
            interfacestats = nsxtT0.getInterfacesStats()
            cpustats = getCpuStats(nodes=nodes)
            #check to make sure old dataframe exists
            if (count == 1):
                #create new frame for delta values
                delta_frame = pandas.DataFrame(columns= interfacestats.columns)
                #loop through rows
                for index, row in interfacestats.iterrows():
                    #find coresponding row in old
                    df2row = interfacestatsold.loc[interfacestatsold['t0_interface']==row['t0_interface']]
                    #add new row to delta
                    delta_frame = delta_frame.append(pandas.Series(dtype='float64'),ignore_index=True)
                    #loop through cols
                    for col_name, value in row.items():
                        #try to set numerical value.  on error assum string
                        try:
                            elapsed_s = (int(df2row['last_update_timestamp'])-int(row['last_update_timestamp']))/1000
                            delta_frame.loc[len(delta_frame.index)-1][col_name]=(int(df2row[col_name])-int(row[col_name]))/elapsed_s
                        except:
                            delta_frame.loc[len(delta_frame.index)-1][col_name]=value
                #write to disk with header if new append if exists
                if os.path.isfile(interface_csv):
                    delta_frame.to_csv(interface_csv, index=False, mode="a",header=False)
                else:
                    delta_frame.to_csv(interface_csv, index=False, mode="a",header=True)
                if os.path.isfile(cpu_csv):
                    cpustats.to_csv(cpu_csv, index=False,mode="a",header=False)
                else:
                    cpustats.to_csv(cpu_csv, index=False,mode="a",header=True)
                #make copy of frame for next lop
                interfacestatsold = interfacestats.copy(deep=True)
            else:
                #make old frame if not exiting
                interfacestatsold = interfacestats.copy(deep=True)
        except Exception as e:
            print(e)
            logger.debug(e)
            break
        #set 1 after first run
        count = 1
        #sleep for 60 seconds
        sleep(60)
    return


if __name__ == '__main__':
    main()
