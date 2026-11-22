#!/bin/sh
# Moves the Coral USB gadget network out of 192.168.100.0/24.
#
# Mendel ships usb0 = 192.168.100.2/24 and usb1 = 192.168.101.2/24. When the
# local network is also 192.168.100.0/24, the usb0 route (metric 100) wins over
# wlan0 (600): the board answers the LAN through the USB cable and, without the
# cable, it looks offline. This script moves the gadget to 192.168.200.0/24 and
# 192.168.201.0/24 (NetworkManager + dnsmasq DHCP ranges).
#
# Idempotent: running it again finishes whatever is still pending.
# It drops any SSH session that goes through the USB cable: run it detached.
set -eu

USB0_NEW=192.168.200
USB1_NEW=192.168.201
DNSMASQ=/etc/dnsmasq.d/02-usb-gadget
# Outside /etc/dnsmasq.d: dnsmasq loads every file in that directory.
BACKUP=/var/backups/dnsmasq-02-usb-gadget.orig

move() {  # move <connection> <old prefix> <new prefix>
    current=$(nmcli -g ipv4.addresses connection show "$1" 2>/dev/null || true)
    case "$current" in
        "$2".*)
            echo "$1: $current -> $3.2/24"
            sudo -n nmcli connection modify "$1" ipv4.addresses "$3.2/24"
            ;;
        *) echo "$1: $current" ;;
    esac
}

move gadget0 192.168.100 "$USB0_NEW"
move gadget1 192.168.101 "$USB1_NEW"

# Clean up the backup left inside the directory by the first version of this script.
if [ -f "$DNSMASQ.orig" ]; then
    sudo -n mv "$DNSMASQ.orig" "$BACKUP"
fi

if [ -f "$DNSMASQ" ] && grep -q "192\.168\.10[01]\." "$DNSMASQ"; then
    [ -f "$BACKUP" ] || sudo -n cp "$DNSMASQ" "$BACKUP"
    sudo -n sed -i -e "s/192\.168\.100\./$USB0_NEW./g" -e "s/192\.168\.101\./$USB1_NEW./g" "$DNSMASQ"
    echo "DHCP USB actualizado en $DNSMASQ (copia en $BACKUP)"
fi

# Apply: interfaces whose live address does not match get their connection re-activated.
for pair in "usb0 gadget0 $USB0_NEW" "usb1 gadget1 $USB1_NEW"; do
    set -- $pair
    if ! ip -4 addr show "$1" 2>/dev/null | grep -q "inet $3\.2/"; then
        echo "Reactivando $2"
        sudo -n nmcli connection up "$2" >/dev/null 2>&1 || echo "$2: sin cable, se aplicará al conectar"
    fi
done

sudo -n systemctl restart dnsmasq
systemctl is-active dnsmasq
echo "Red USB lista: la placa está en $USB0_NEW.2 por USB."
