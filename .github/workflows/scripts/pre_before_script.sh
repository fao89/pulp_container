set -mveuo pipefail

cat /etc/hosts | grep pulp
PULP_HOSTNAME=$(cat /etc/hosts | sed -En "s/pulp/pulp.example.com/p")
echo $PULP_HOSTNAME | sudo tee -a /etc/hosts
cat /etc/hosts | grep pulp

echo "machine pulp.example.com
login admin
password password

machine pulp
login admin
password password
" > ~/.netrc

sed -i 's/http:\/\/pulp/http:\/\/pulp.example.com/g' $PWD/.github/workflows/scripts/script.sh
