#!/bin/bash
# Close k3s
function stop_container {
        supervisorctl stop k3s
        docker ps | awk '{print $1}' | sed '1d' | xargs docker stop
        exit 0
}
# Function to stop execution after receiving the signal
trap stop_container SIGTERM

# unzip the image
image=$(docker images | grep api | awk '{print $1}')
if [[ $image != "registry.cn-hangzhou.aliyuncs.com/goodrain/rbd-api" ]];then
 while true; do
        docker load -i /app/ui/rainbond.tar
        if [ $? -eq 0 ]; then
                break
        fi
 done
fi


#Start K3s 

/usr/local/bin/k3s server --docker --disable traefik --node-name node --data-dir /app/data/k3s
