pid_file = "/run/shms-vault-web/vault-agent.pid"

vault {
  address = "https://vault.shms.local:8200"
  ca_cert = "/opt/nautobot/certs/vault-ca.crt"
}

auto_auth {
  method "cert" {
    mount_path = "auth/cert"

    config = {
      name = "shms-nautobot-web"
      client_cert = "/opt/nautobot/certs/vault-agent/nautobot-service.crt"
      client_key = "/opt/nautobot/certs/vault-agent/nautobot-service.key"
    }
  }

  sink "file" {
    config = {
      path = "/run/shms-vault-web/nautobot.token"
      mode = 0644
    }
  }
}
