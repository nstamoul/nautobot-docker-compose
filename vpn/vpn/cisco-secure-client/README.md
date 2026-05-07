# Cisco Secure Client build artifacts

The SHMS VPN image intentionally bundles the licensed Cisco Secure Client Linux
VPN installer artifacts from this directory. This keeps local and CI image builds
deterministic and avoids requiring a separate artifact handoff at build time.

Only the approved Linux predeploy tarballs should be tracked here. Do not add
unpacked installer contents or ad hoc local downloads.

Supported artifact shapes:

- a Cisco predeploy `.tgz` containing `cisco-secure-client-vpn-cli_*_amd64.deb`
- a Cisco predeploy `.tgz` containing `cisco-secure-client-vpn-cli_*_arm64.deb`
- a standalone `.deb` package matching the build target architecture
- a `.tar.gz` or `.tgz` bundle containing `vpn_install.sh`
- an extracted directory containing `vpn_install.sh`

The Dockerfile selects artifacts using Docker BuildKit `TARGETARCH` and installs
the CLI package only. If this directory contains no matching installer, the image
still builds, but selecting `VPN_CLIENT=cisco-secure-client` fails at runtime
with a clear missing-binary error.
