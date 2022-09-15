#!/usr/bin/env bash
echo "###########################################################################################"
podman pull ghcr.io/pulp/test-fixture-1:manifest_a

# push a tagged image to the registry
podman login --tls-verify=false -u admin -p password ${REGISTRY_ADDR}
podman tag ghcr.io/pulp/test-fixture-1:manifest_a \
  ${REGISTRY_ADDR}/test/fixture:manifest_a
podman push --tls-verify=false ${REGISTRY_ADDR}/test/fixture:manifest_a

# a repository of the push type is automatically created
REPOSITORY_HREF=$(pulp container repository -t push show \
  --name "test/fixture" | jq -r ".pulp_href")
echo $REPOSITORY_HREF
# export the repository to the directory '/tmp/exports/test-fixture'
EXPORTER_JSON=$(http ${BASE_ADDR}/pulp/api/v3/exporters/core/pulp/ \
  name=both repositories:="[\"${REPOSITORY_HREF}\"]" \
  path=/tmp/exports/test-fixture)
echo $EXPORTER_JSON
EXPORTER_HREF=$(echo $EXPORTER_JSON | jq -r ".pulp_href")
echo $EXPORTER_HREF
TASK_HREF=$(http POST ${BASE_ADDR}${EXPORTER_HREF}exports/ | jq -r ".task")
echo $TASK_HREF
wait_until_task_finished ${BASE_ADDR}${TASK_HREF}
