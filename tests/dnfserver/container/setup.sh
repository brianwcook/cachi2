#!/bin/bash
echo "I'm alive!" > /certificates/index.html
chown $myuser:nginx /certificates
chmod 770 /certificates
chown -R nginx:nginx "/certificates"

# put certs in place
mkdir "/etc/pki/nginx"
chown -R nginx:nginx "/etc/pki/nginx"
chmod 700 "/etc/pki/nginx"

cp /certificates/localhost.crt "/etc/pki/nginx/server.crt"
cp /certificates/localhost.key "/etc/pki/nginx/server.key"
cp /certificates/myCA.crt "/etc/pki/myCA.crt"

# create yum repo
pip3 install createrepo_c
mkdir -p /dnfrepo/pkg
mkdir /dnfrepo/source
echo "I'm alive!" > /dnfrepo/index.html
chmod 700 "/dnfrepo"
cd /dnfrepo/pkg
curl -O https://cdn-ubi.redhat.com/content/public/ubi/dist/ubi9/9/x86_64/baseos/os/Packages/r/redhat-release-9.4-0.5.el9.x86_64.rpm
createrepo_c .
cd /dnfrepo/source
curl -O https://cdn-ubi.redhat.com/content/public/ubi/dist/ubi9/9/x86_64/baseos/source/SRPMS/Packages/r/redhat-release-9.4-0.5.el9.src.rpm
createrepo_c .
chown -R nginx:nginx "/dnfrepo"
