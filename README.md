# Indigo-LG-WebOS-Plugin
Indigo Plugin for LG WebOS TV's

This is an Indigo Plugin for the LG WebOS. I’m using a TV that is kind of old, but am thinking it should work with any TV that runs WebOS. The original purpose of the plugin was to basically automate turning the TV on and off with other entertainment devices, since I use the TV mainly as just a dumb monitor. However, there are some provisions for changing inputs, channels and adjusting the volume as well. 

I am not a “coder” and used AI to write the whole thing. Both the WebOS is pretty well documented, and AI seems to have a good grasp of how to write plugins for Indigo. 

In short, you’ll need to manually install the web socket client

1. Install Pip
	$ wget https://bootstrap.pypa.io/get-pip.py

2. Then run the installer:
	$ python3 ./get-pip.py

3. Then install the web socket-client.
	pip install websocket-client

4. Download and double click the plugin to install
5. Add a New Device in Indigo from on the plugin by entering your TV’s IP address
6. Click “Pair With TV” in Indigo, and then 
7, On your TV accept the prompt on your TV screen.
8. Add your TV’s MAC address for Wake-On-LAN power on support

Please feel free to make changes to this plugin. 
