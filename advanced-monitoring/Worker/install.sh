#!/bin/bash
export `curl -H Metadata:true --noproxy "*" "http://169.254.169.254/metadata/instance/compute/userData?api-version=2021-01-01&format=text" | base64 --decode`
if [[ -z ${AVS_CLOUD_ID+x} ]]; then
  while getopts ":p:c:" opt; do
    case $opt in
      p) install_path="$OPTARG"
      ;;
      c) cloud_id="$OPTARG"
      ;;
      \?) echo "Invalid option -$OPTARG" >&2
      exit 1
      ;;
    esac

    case $OPTARG in
      -*) echo "Option $opt needs a valid argument"
      exit 1
      ;;
    esac
  done
else
  export install_path=/opt/nsx-stat
  export cloud_id=$AVS_CLOUD_ID
fi
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
echo Installing to $install_path
echo Cloud $cloud_id
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt install wget
wget -qO- https://repos.influxdata.com/influxdb.key | tee /etc/apt/trusted.gpg.d/influxdb.asc >/dev/null
source /etc/os-release && echo "deb https://repos.influxdata.com/${ID} ${VERSION_CODENAME} stable" | tee /etc/apt/sources.list.d/influxdb.list
apt-get update
apt-get install python3-pip python3-venv telegraf -y
service telegraf stop
systemctl disable telegraf.service
mkdir $install_path
cd $SCRIPT_DIR
cp main.py $install_path
cp requirements.txt $install_path
cp telegraf.conf $install_path
cp nsx-stat.service $install_path
cp start.sh $install_path
cp get_cloud_info.py $install_path
cp get_info.sh $install_path
cp crontab $install_path
chmod +x $install_path/start.sh
cd $install_path
sed -i "s~##WORKINGDIR##~$install_path~" $install_path/get_info.sh
chmod +x $install_path/get_info.sh
python3 -m venv venv
source ./venv/bin/activate
python3 -m pip install -r requirements.txt
sed -i "s~##WORKINGDIR##~$install_path~" nsx-stat.service
sed -i "s~##CLOUDID##~$cloud_id~" nsx-stat.service
cp nsx-stat.service /etc/systemd/system/
systemctl daemon-reload
sed -i "s~/##WORKINGDIR##~$install_path~" $install_path/telegraf.conf
sed -i "s~/##WORKINGDIR##~$install_path~" $install_path/crontab
crontab crontab
cp $install_path/telegraf.conf /etc/telegraf/
systemctl enable nsx-stat.service
systemctl start nsx-stat