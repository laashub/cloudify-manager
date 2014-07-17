#!/bin/bash

set -e

echo "### Action: $ACTION"
echo "### arg: $1"

echo "### Creating agent package..."
mkdir -p package/linux
virtualenv package/linux/env
source package/linux/env/bin/activate

git clone https://github.com/cloudify-cosmo/cloudify-rest-client --depth=1
cd cloudify-rest-client; pip install .; cd ..

git clone https://github.com/cloudify-cosmo/cloudify-plugins-common --depth=1
cd cloudify-plugins-common; pip install .; cd ..

cd plugins/agent-installer && pip install . && cd ../..
cd plugins/windows-agent-installer && pip install . && cd ../..
cd plugins/plugin-installer && pip install . && cd ../..
cd plugins/windows-plugin-installer && pip install . && cd ../..
cd plugins/agent-installer/worker_installer/tests/mock-sudo-plugin && pip install . && cd ../../../../..
tar czf Ubuntu-agent.tar.gz package
rm -rf package

virtualenv ~/env
source ~/env/bin/activate

pip install nose
pip install fabric

cd cloudify-rest-client; pip install .; cd ..
cd cloudify-plugins-common; pip install .; cd ..
cd plugins/windows-agent-installer; pip install .; cd ../..
cd plugins/windows-plugin-installer; pip install .; cd ../..

echo "### Starting HTTP server for serving agent package (for agent installer tests)"
python -m SimpleHTTPServer 8000 &

nosetests plugins/plugin-installer/plugin_installer/tests --nologcapture --nocapture
nosetests plugins/windows-plugin-installer/windows_plugin_installer/tests --nologcapture --nocapture
nosetests plugins/windows-agent-installer/windows_agent_installer/tests --nologcapture --nocapture

echo "Defaults:travis  requiretty" | sudo tee -a /etc/sudoers
cd plugins/agent-installer
nosetests worker_installer.tests.test_configuration:CeleryWorkerConfigurationTest --nologcapture --nocapture
nosetests worker_installer.tests.test_worker_installer:TestLocalInstallerCase --nologcapture --nocapture
cd ..
