// Title: Azure VMware Solution Private Cloud Syslog Forwarding Node.js function for Azure Function App

// Purpose: Azure Function App pulls messages from the Azure Event Hub and forwards them to a Syslog server with the Syslog protocol.

module.exports = function (context, myEventHubMessage) {
    context.log(`JavaScript eventhub trigger function called for message JSON string ${myEventHubMessage}`);
    // Initializing syslog-client, which is installed using the "npm install syslog-client" command.
    try{
        var syslog = require("syslog-client");
    } catch (e) {
        throw e;
    }    

    // Get environment variables which are defined in the Azure Function App Application Settings.
    var SYSLOG_SERVER = GetEnvironmentVariable("SYSLOG_SERVER");

    var SYSLOG_PORT = GetEnvironmentVariable("SYSLOG_PORT");

    // If key environment variables are not configured, throw an error. Remaining environment variables are assigned a default value if null.
    if ((SYSLOG_SERVER == null) || (SYSLOG_PORT == null)) {
        throw "Please setup SYSLOG_SERVER and/or SYSLOG_PORT environment variables. "
    }

    var SYSLOG_PROTOCOL;
    if (GetEnvironmentVariable("SYSLOG_PROTOCOL")=="TCP") {
        SYSLOG_PROTOCOL = syslog.Transport.Tcp;
		context.log('*** Syslog TCP');
    } else {
        SYSLOG_PROTOCOL = syslog.Transport.Udp;
		context.log('*** Syslog UDP');
    }

    var SYSLOG_HOSTNAME;
    if (GetEnvironmentVariable("SYSLOG_HOSTNAME")==null) {
        SYSLOG_HOSTNAME = "azurefunction"
    } else {
        SYSLOG_HOSTNAME = GetEnvironmentVariable("SYSLOG_HOSTNAME");
		context.log('*** Syslog hostname', SYSLOG_HOSTNAME);
    }

    var SYSLOG_FACILITY;
    if (GetEnvironmentVariable("SYSLOG_FACILITY")==null) {
        SYSLOG_FACILITY = syslog.Facility.Local0;
    } else {
        SYSLOG_FACILITY = GetEnvironmentVariable("SYSLOG_FACILITY");
    }

    // Options for syslog connection which are defined in the Azure Function App Application Settings.
    var options = {
        syslogHostname: SYSLOG_HOSTNAME,
        transport: SYSLOG_PROTOCOL,    
        port: SYSLOG_PORT,
        facility: SYSLOG_FACILITY
    };

    // Log connection variables which are defined in the Azure Function App Application Settings.
    context.log('SYSLOG Server: ', SYSLOG_SERVER);
    context.log('SYSLOG Port: ', SYSLOG_PORT);
    context.log('SYSLOG Protocol: ', SYSLOG_PROTOCOL);
    context.log('SYSLOG Hostname: ', SYSLOG_HOSTNAME);
    context.log('SYSLOG Facility: ', SYSLOG_FACILITY);

    // Log received message from Azure Event Hub. Azure Event Hub is the configured Azure VMware Solution Diagnostic log target.
    context.log(`Event Hubs trigger function processed message:  ${myEventHubMessage}`);
    context.log('EnqueuedTimeUtc =', context.bindingData.enqueuedTimeUtc);
    context.log('SequenceNumber =', context.bindingData.sequenceNumber);
    context.log('Offset =', context.bindingData.offset);
    
    // Create syslog client, which is installed using the "npm install syslog-client" command.
    var client = syslog.createClient(SYSLOG_SERVER, options);

    // Cycle through Azure Event Hub messages and send messages with Syslog protocol to configured Syslog server.
	// Azure Event Hub sends the messages in JSON.string format.
    myEventHubMessage.forEach((message, index)=>{
        if(typeof message === 'string'){
            var msg = JSON.parse(message);			
			msg.records.forEach((m1, i) => {
                client.log(JSON.stringify(m1), options, function(error) {        
                    if (error) {
                        context.log("error sending message");
                        context.log(error);
                    } else {
                        context.log("sent message successfully");
                    }
                });
            });           
        }
    });

    context.log("completed sending all messages");
    context.done();
};

// Get environment variables defined in the Azure Function App Application Settings.
function GetEnvironmentVariable(name)
{
    return process.env[name];
}
