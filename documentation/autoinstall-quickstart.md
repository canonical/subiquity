# Autoinstall Quick Start

The intent of this page is to provide simple instructions to perform an autoinstall in a VM on your machine.

This page assumes that you are willing to install the latest Ubuntu release available i.e., 22.10 at the time of writing. For other releases, you would need to substitute the name of the ISO image but the instructions should otherwise remain the same.

This page also assumes you are on the amd64 architecture. There is a version for [s390x](autoinstall-quickstart-s390x.md) too.

## Providing the autoinstall data over the network

This method is the one that generalizes most easily to doing an entirely network-based install, where a machine netboots and then is automatically installed.

### Download the ISO

Go to the [22.10 ISO download page](https://releases.ubuntu.com/22.10/) and download the latest Ubuntu 22.10 live-server ISO.

### Mount the ISO

<pre><code>sudo mount -r ~/Downloads/ubuntu-22.10-live-server-amd64.iso /mnt</code></pre>

### Write your autoinstall config

This means creating cloud-init config as follows:

<pre><code>mkdir -p ~/www
cd ~/www
cat > user-data << 'EOF'
#cloud-config
autoinstall:
  version: 1
  identity:
    hostname: ubuntu-server
    password: "$6$exDY1mhS4KUYCE/2$zmn9ToZwTKLhCw.b4/b.ZRTIZM30JZ4QrOQ2aOXJ8yk96xpcCof0kxKwuX1kqLG/ygbJ1f8wxED22bTL4F46P0"
    username: ubuntu
EOF
touch meta-data</code></pre>

The crypted password is just "ubuntu".

### Serve the cloud-init config over http

Leave this running in one terminal window:

<pre><code>cd ~/www
python3 -m http.server 3003</code></pre>

### Create a target disk

<pre><code>truncate -s 10G image.img</code></pre>

### Run the install!

<pre><code>kvm -no-reboot -m 2048 \
    -drive file=image.img,format=raw,cache=none,if=virtio \
    -cdrom ~/Downloads/ubuntu-22.10-live-server-amd64.iso \
    -kernel /mnt/casper/vmlinuz \
    -initrd /mnt/casper/initrd \
    -append 'autoinstall ds=nocloud-net;s=http://_gateway:3003/'</code></pre>

This will boot, download the config from the server set up in the previous step and run the install. The installer reboots at the end but the -no-reboot flag to kvm means that kvm will exit when this happens. It should take about 5 minutes.

### Boot the installed system

<pre><code>kvm -no-reboot -m 2048 \
    -drive file=image.img,format=raw,cache=none,if=virtio</code></pre>

This will boot into the freshly installed system and you should be able to log in as ubuntu/ubuntu.

## Using another volume to provide the autoinstall config

This is the method to use when you want to create media that you can just plug into a system to have it be installed.

### Download the live-server ISO

Go to the [22.10 ISO download page](https://releases.ubuntu.com/22.10/) and download the latest Ubuntu 22.10 live-server ISO.

### Create your user-data & meta-data files

<pre><code>mkdir -p ~/cidata
cd ~/cidata
cat > user-data << 'EOF'
#cloud-config
autoinstall:
  version: 1
  identity:
    hostname: ubuntu-server
    password: "$6$exDY1mhS4KUYCE/2$zmn9ToZwTKLhCw.b4/b.ZRTIZM30JZ4QrOQ2aOXJ8yk96xpcCof0kxKwuX1kqLG/ygbJ1f8wxED22bTL4F46P0"
    username: ubuntu
EOF
touch meta-data</code></pre>

The crypted password is just "ubuntu".

### Create an ISO to use as a cloud-init data source

<pre><code>sudo apt install cloud-image-utils
cloud-localds ~/seed.iso user-data meta-data</code></pre>

### Create a target disk

<pre><code>truncate -s 10G image.img</code></pre>

### Run the install!

<pre><code>kvm -no-reboot -m 2048 \
    -drive file=image.img,format=raw,cache=none,if=virtio \
    -drive file=~/seed.iso,format=raw,cache=none,if=virtio \
    -cdrom ~/Downloads/ubuntu-22.10-live-server-amd64.iso</code></pre>

This will boot and run the install. Unless you interrupt boot to add 'autoinstall' to the kernel command line, the installer will prompt for confirmation before touching the disk.

The installer reboots at the end but the -no-reboot flag to kvm means that kvm will exit when this happens.

The whole process should take about 5 minutes.

### Boot the installed system

<pre><code>kvm -no-reboot -m 2048 \
    -drive file=image.img,format=raw,cache=none,if=virtio</code></pre>

This will boot into the freshly installed system and you should be able to log in as ubuntu/ubuntu.
