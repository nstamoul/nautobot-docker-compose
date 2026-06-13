pid_file = "/run/shms-vault-beat/vault-agent.pid"

vault {
  address = "https://vault.shms.local:8200"
  ca_cert = "/opt/nautobot/certs/vault-ca.crt"
}

auto_auth {
  method "cert" {
    mount_path = "auth/cert"

    config = {
      name = "shms-nautobot-beat"
      client_cert = "/opt/nautobot/certs/vault-agent/nautobot-service.crt"
      client_key = "/opt/nautobot/certs/vault-agent/nautobot-service.key"
    }
  }

  sink "file" {
    config = {
      path = "/run/shms-vault-beat/beat.token"
      mode = 0644
    }
  }
}
