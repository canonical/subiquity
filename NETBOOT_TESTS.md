# Testing changes with netboot

The ISO tracker already contains [test cases for performing netboot](https://iso.qa.ubuntu.com/qatracker/milestones/454/builds/304977/testcases/1734/results), but the setup can be cumbersome when iterating. This is a quick guide for using QEMU and Apache to perform VM-based netboot tests.

## Serving your custom ISO

When netbooting the installer you will need to decide where to point the bootloader to download the ISO from. The simplest and fastest way to serve your custom ISO is to install `apache2` on your machine, copy the ISO to `/var/www/html/`, and then point QEMU to your machine on your local network.

1. Install apache2:
```bash
sudo apt install -y apache2
```

2. Copy your ISO to the public directory:

```bash
cp /tmp/my-custom-image.iso /var/www/html/.
```

3. Visit `http://localhost/my-custom-image.iso` in a web-browser and make sure the download starts.

4. Get the local IP of your machine (or whichever host is serving the ISO) using `ip` or similar. It will be used for the next step.

## Setting up the tftp directory

We will utilize QEMU's built in tftp server so we don't have to worry about setting up the server, but we still have to ensure the tftp directory is setup correctly.

1. Download the prebuilt netboot artifacts from cdimage or releases.ubuntu.com.

```bash
wget -O /tmp/netboot-artifacts.tar.gz https://releases.ubuntu.com/noble/ubuntu-24.04-netboot-amd64.tar.gz
```

2. Unpack it.
```bash
mkdir /tmp/tftp
tar -zxvf /tmp/netboot-artifacts.tar.gz -C /tmp/tftp/
```

3. Update kernel and initrd in the tftp directory with the ones from your ISO. (If you are testing server and are using the netboot artifacts that were published with the original ISO you modified, you can skip this step.)
```bash
sudo mkdir /mnt/my-custom-image
sudo mount /tmp/my-custom-image.iso /mnt/my-custom-image
sudo cp /mnt/my-custom-image/casper/vmlinuz /tmp/tftp/amd64/linux
sudo cp /mnt/my-custom-image/casper/initrd /tmp/tftp/amd64/initrd
sudo umount /mnt/my-custom-image
```

4. Replace the URL pointed to by `iso-url` in `/tmp/tftp/amd64/grub/grub.cfg` and `/tmp/tftp/amd64/pxelinux.cfg/default` with `http://<iso-server-ip>/my-custom-image.iso`. Note the usage of *http* and __not__ *https*.


## Starting QEMU

QEMU can start up a tftp server by passing the tftp directory to one of the NICs on the virtual machine.

- When using UEFI bios, pass `-nic <other options>,tftp=/tmp/tftp/amd64,bootfile=bootx64.efi`.
- When using non-UEFI bios, pass `-nic <other options>,tftp=/tmp/tftp/amd64,bootfile=pxelinux.0`.

The `kvm-test.py` script currently doesn't support netbooting (it requires passing an ISO to mount to `/cdrom`), but you can use it to generate the command line arguments and then modify the `-nic` argument accordingly.

An example invocation for booting a desktop image:
```bash
qemu-img create -f qcow2 /tmp/kvm-test/edge-test.img 20G
kvm -no-reboot -vga virtio -m 14G -bios /usr/share/qemu/OVMF.fd -nic user,model=virtio-net-pci,hostfwd=tcp::2222-:22,tftp=/tmp/tftp/amd64,bootfile=bootx64.efi -device qxl -smp 2 -drive file=/tmp/kvm-test/edge-test.img,format=qcow2,cache=writethrough,if=virtio
```

## Extras

- QEMU requires enough allocated RAM to both download the ISO and unpack it, so you need to allocate a little over 2x the size of the image.
- If you encounter an error after downloading the image in the VM that states `unable to find a live file system on the network` then it's likely the initrd and/or kernel (`vmlinuz`/`linux`) in the tftp directory do not match what is on the ISO. See [LP:#1969970](https://bugs.launchpad.net/ubuntu/+source/casper/+bug/1969970).

