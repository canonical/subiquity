#!/bin/bash
BOOT=firstboot.raw
SEED=seed.img

[ ! -e ${SEED} ] && {
    cat > user-data <<EOF 
#cloud-config
password: passw0rd
chpasswd: { expire: False }
ssh_pwauth: True
EOF
    echo "instance-id: $(uuidgen || echo i-abcdefg)" > meta-data
    cloud-localds ${SEED} user-data meta-data
}

qemu-system-x86_64 -m 1024 --enable-kvm \
  -snapshot \
  -drive file=${BOOT},format=raw,if=virtio \
  -net user -net nic,model=virtio \
  -redir tcp:2222::22 \
  -cdrom $SEED \
  -monitor stdio \
  -serial telnet:localhost:2447,nowait,server
