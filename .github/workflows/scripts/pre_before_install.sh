set -mveuo pipefail


update_docker_configuration() {
  echo "INFO:
  Updating docker configuration
  "

  echo '{
  "insecure-registries" : ["pulp.example.com:80", "pulp.example.com"],
  "cgroup-parent": "/actions_job"
}' | sudo tee /etc/docker/daemon.json
  sudo service docker restart
}

update_podman_configuration() {
  echo "INFO:
  Updating podman configuration
  "
  echo "[registries.insecure]" | sudo tee -a /etc/containers/registries.conf
  echo "registries = ['pulp.example.com:80']" | sudo tee -a /etc/containers/registries.conf
  podman info
}

update_docker_configuration
update_podman_configuration
