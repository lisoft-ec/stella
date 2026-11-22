#!/bin/sh
# Moves the Coral USB gadget network out of 192.168.100.0/24.
#
# Mendel ships usb0 = 192.168.100.2/24 and usb1 = 192.168.101.2/24. When the
# local network is also 192.168.100.0/24, the usb0 route (metric 100) wins over
# wlan0 (600): the board answers the LAN through the USB cable and, without the
# cable, it looks offline. This script moves the gadget to 192.168.200.0/24 and
# 192.168.201.0/24 (NetworkManager + dnsmasq DHCP ranges). It is idempotent.
#
# It drops any SSH session that goes through the USB cable: run it detached.
set -eu

USB0_NEW=192.168.200
USB1_NEW=192.168.201
DNSMASQ=/etc/dnsmasq.d/02-usb-gadget

changed=0

move() {  # move <connection> <old prefix> <new prefix>
    current=$(nmcli -g ipv4.addresses connection show "$1" 2>/dev/null || true)
    case "$current" in
        "$2".*)
            echo "$1: $current -> $3.2/24"
            sudo -n nmcli connection modify "$1" ipv4.addresses "$3.2/24"
            changed=1
            ;;
        *) echo "$1: $current (sin cambios)" ;;
    esac
}

move gadget0 192.168.100 "$USB0_NEW"
move gadget1 192.168.101 "$USB1_NEW"

if [ -f "$DNSMASQ" ] && grep -q "192\.168\.10[01]\." "$DNSMASQ"; then
    [ -f "$DNSMASQ.orig" ] || sudo -n cp "$DNSMASQ" "$DNSMASQ.orig"
    sudo -n sed -i -e "s/192\.168\.100\./$USB0_NEW./g" -e "s/192\.168\.101\./$USB1_NEW./g" "$DNSMASQ"
    echo "DHCP USB actualizado en $DNSMASQ"
    changed=1
fi

if [ "$changed" = 1 ]; then
    sudo -n systemctl restart dnsmasq
    sudo -n nmcli connection up gadget0 >/dev/null 2>&1 || true
    sudo -n nmcli connection up gadget1 >/dev/null 2>&1 || true
    echo "Red USB movida: ahora la placa está en $USB0_NEW.2 por USB."
fi
