pid_file = "/run/shms-vault-celery/vault-agent.pid"

vault {
  address = "https://vault.shms.local:8200"
  ca_cert = "/opt/nautobot/certs/vault-ca.crt"
}

auto_auth {
  method "cert" {
    mount_path = "auth/cert"

    config = {
      name = "shms-nautobot-celery"
      client_cert = "/opt/nautobot/certs/vault-agent/nautobot-service.crt"
      client_key = "/opt/nautobot/certs/vault-agent/nautobot-service.key"
    }
  }

  sink "file" {
    config = {
      path = "/run/shms-vault-celery/celery.token"
      mode = 0644
    }
  }
}
