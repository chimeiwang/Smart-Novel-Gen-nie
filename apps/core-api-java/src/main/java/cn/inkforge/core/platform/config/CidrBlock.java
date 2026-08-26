package cn.inkforge.core.platform.config;

import java.net.InetAddress;
import java.util.Arrays;

/** 不触发 DNS 的 IPv4/IPv6 CIDR。 */
public final class CidrBlock {

    private final byte[] network;
    private final int prefixLength;
    private final String normalized;

    private CidrBlock(byte[] network, int prefixLength, String normalized) {
        this.network = network;
        this.prefixLength = prefixLength;
        this.normalized = normalized;
    }

    public static CidrBlock parse(String value) {
        try {
            String[] parts = value.strip().split("/", -1);
            if (parts.length != 2 || !isIpLiteral(parts[0])) {
                throw new IllegalArgumentException();
            }
            byte[] address = InetAddress.getByName(parts[0]).getAddress();
            int prefix = Integer.parseInt(parts[1]);
            if (prefix < 0 || prefix > address.length * 8) {
                throw new IllegalArgumentException();
            }
            byte[] network = masked(address, prefix);
            String normalized = normalizeBytes(network) + "/" + prefix;
            return new CidrBlock(network, prefix, normalized);
        } catch (Exception exception) {
            throw new IllegalArgumentException("CIDR 无效");
        }
    }

    public boolean contains(String addressText) {
        try {
            if (!isIpLiteral(addressText)) {
                return false;
            }
            byte[] address = InetAddress.getByName(addressText).getAddress();
            return address.length == network.length && Arrays.equals(masked(address, prefixLength), network);
        } catch (Exception exception) {
            return false;
        }
    }

    public static String normalizeAddress(String addressText) {
        try {
            if (!isIpLiteral(addressText)) {
                throw new IllegalArgumentException();
            }
            return normalizeBytes(InetAddress.getByName(addressText).getAddress());
        } catch (Exception exception) {
            throw new IllegalArgumentException("IP 地址无效");
        }
    }

    @Override
    public String toString() {
        return normalized;
    }

    private static byte[] masked(byte[] value, int prefixLength) {
        byte[] result = value.clone();
        int fullBytes = prefixLength / 8;
        int remainingBits = prefixLength % 8;
        if (remainingBits != 0 && fullBytes < result.length) {
            result[fullBytes] &= (byte) (0xff << (8 - remainingBits));
            fullBytes++;
        }
        Arrays.fill(result, fullBytes, result.length, (byte) 0);
        return result;
    }

    private static boolean isIpLiteral(String value) {
        if (value == null || value.isBlank() || value.contains("%")) {
            return false;
        }
        if (value.contains(":")) {
            return value.matches("[0-9A-Fa-f:.]+");
        }
        String[] octets = value.split("\\.", -1);
        if (octets.length != 4) {
            return false;
        }
        try {
            return Arrays.stream(octets)
                    .allMatch(item -> item.matches("[0-9]{1,3}") && Integer.parseInt(item) <= 255);
        } catch (NumberFormatException exception) {
            return false;
        }
    }

    private static String normalizeBytes(byte[] bytes) {
        if (bytes.length == 4) {
            return (bytes[0] & 0xff)
                    + "."
                    + (bytes[1] & 0xff)
                    + "."
                    + (bytes[2] & 0xff)
                    + "."
                    + (bytes[3] & 0xff);
        }
        int[] groups = new int[8];
        for (int index = 0; index < groups.length; index++) {
            groups[index] = ((bytes[index * 2] & 0xff) << 8) | (bytes[index * 2 + 1] & 0xff);
        }
        int bestStart = -1;
        int bestLength = 0;
        for (int start = 0; start < groups.length; ) {
            if (groups[start] != 0) {
                start++;
                continue;
            }
            int end = start;
            while (end < groups.length && groups[end] == 0) {
                end++;
            }
            if (end - start > bestLength && end - start >= 2) {
                bestStart = start;
                bestLength = end - start;
            }
            start = end;
        }
        StringBuilder result = new StringBuilder();
        for (int index = 0; index < groups.length; index++) {
            if (index == bestStart) {
                result.append("::");
                index += bestLength - 1;
                continue;
            }
            if (!result.isEmpty() && result.charAt(result.length() - 1) != ':') {
                result.append(':');
            }
            result.append(Integer.toHexString(groups[index]));
        }
        return result.toString();
    }
}
