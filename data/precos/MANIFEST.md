# Manifesto da captura de preços — IBM Cloud e AWS, São Paulo

> Gerado por `src/run_capture.py --manifesto` em 2026-08-13T20:59:06+00:00, **lendo os corpos crus em disco**. Cobertura conferida contra a lista selada em `configs/projeto-tecnico.json`.

| Provedor | Serviço | Plano / fatia | Região do preço | Item de custo | Arquivo | Bytes | Métricas com preço |
|---|---|---|---|---|---|---|---|
| IBM | `is.instance` | `bxf-2x8` | br-sao | compute | `data/precos/api/ibm-is.instance-bxf-2x8-br-sao-2026-08-13.json` | 131311 | 10 |
| IBM | `is.instance` | `bxf-4x16` | br-sao | compute | `data/precos/api/ibm-is.instance-bxf-4x16-br-sao-2026-08-13.json` | 131299 | 10 |
| IBM | `is.instance` | `bxf-8x32` | br-sao | compute | `data/precos/api/ibm-is.instance-bxf-8x32-br-sao-2026-08-13.json` | 131356 | 10 |
| IBM | `is.instance` | `bxf-16x64` | br-sao | compute | `data/precos/api/ibm-is.instance-bxf-16x64-br-sao-2026-08-13.json` | 131386 | 10 |
| IBM | `is.instance` | `cxf-2x4` | br-sao | compute | `data/precos/api/ibm-is.instance-cxf-2x4-br-sao-2026-08-13.json` | 138968 | 11 |
| IBM | `is.instance` | `cxf-4x8` | br-sao | compute | `data/precos/api/ibm-is.instance-cxf-4x8-br-sao-2026-08-13.json` | 138866 | 11 |
| IBM | `is.instance` | `cxf-8x16` | br-sao | compute | `data/precos/api/ibm-is.instance-cxf-8x16-br-sao-2026-08-13.json` | 138894 | 11 |
| IBM | `is.instance` | `cxf-16x32` | br-sao | compute | `data/precos/api/ibm-is.instance-cxf-16x32-br-sao-2026-08-13.json` | 138970 | 11 |
| IBM | `is.bare-metal-server` | `mx3-metal-16x128` | br-sao | compute-oracle | `data/precos/api/ibm-is.bare-metal-server-mx3-metal-16x128-br-sao-2026-08-13.json` | 125514 | 13 |
| IBM | `is.bare-metal-server` | `mx3d-metal-16x128` | br-sao | compute-oracle | `data/precos/api/ibm-is.bare-metal-server-mx3d-metal-16x128-br-sao-2026-08-13.json` | 125532 | 13 |
| IBM | `is.bare-metal-server` | `vx3-metal-16x256` | br-sao | compute-oracle | `data/precos/api/ibm-is.bare-metal-server-vx3-metal-16x256-br-sao-2026-08-13.json` | 125501 | 13 |
| IBM | `is.bare-metal-server` | `ux3-metal-16x512` | br-sao | compute-oracle | `data/precos/api/ibm-is.bare-metal-server-ux3-metal-16x512-br-sao-2026-08-13.json` | 125520 | 13 |
| IBM | `is.volume` | `gen2-volume-custom` | br-sao | bloco | `data/precos/api/ibm-is.volume-gen2-volume-custom-br-sao-2026-08-13.json` | 17010 | 2 |
| IBM | `is.volume` | `gen2-volume-general-purpose` | br-sao | bloco | `data/precos/api/ibm-is.volume-gen2-volume-general-purpose-br-sao-2026-08-13.json` | 9389 | 1 |
| IBM | `is.volume` | `gen2-volume-10iops-tier` | br-sao | bloco | `data/precos/api/ibm-is.volume-gen2-volume-10iops-tier-br-sao-2026-08-13.json` | 9420 | 1 |
| IBM | `is.volume` | `gen2-volume-5iops-tier` | br-sao | bloco | `data/precos/api/ibm-is.volume-gen2-volume-5iops-tier-br-sao-2026-08-13.json` | 9392 | 1 |
| IBM | `is.load-balancer` | `gen2-load-balancer` | br-sao | rede | `data/precos/api/ibm-is.load-balancer-gen2-load-balancer-br-sao-2026-08-13.json` | 16823 | 2 |
| IBM | `is.load-balancer` | `network-load-balancer-gen2` | br-sao | rede | `data/precos/api/ibm-is.load-balancer-network-load-balancer-gen2-br-sao-2026-08-13.json` | 16912 | 2 |
| IBM | `containers-kubernetes` | `containers-kubernetes-cluster` | br-sao | contêineres | `data/precos/api/ibm-containers-kubernetes-containers-kubernetes-cluster-br-sao-2026-08-13.json` | 2567 | 0 |
| IBM | `containers-kubernetes` | `containers-kubernetes-vpc-bxf-4x16` | br-sao | contêineres | `data/precos/api/ibm-containers-kubernetes-containers-kubernetes-vpc-bxf-4x16-br-sao-2026-08-13.json` | 17248 | 2 |
| IBM | `containers-kubernetes` | `containers-kubernetes-vpc-bxf-8x32` | br-sao | contêineres | `data/precos/api/ibm-containers-kubernetes-containers-kubernetes-vpc-bxf-8x32-br-sao-2026-08-13.json` | 17488 | 2 |
| IBM | `codeengine` | `standard` | não-regional (declarado) | serverless | `data/precos/api/ibm-codeengine-standard-nao-regional-2026-08-13.json` | 106008 | 13 |
| IBM | `databases-for-mysql` | `standard-gen2` | não-regional (declarado) | banco-gerenciado | `data/precos/api/ibm-databases-for-mysql-standard-gen2-nao-regional-2026-08-13.json` | 91786 | 12 |
| IBM | `databases-for-postgresql` | `standard-gen2` | não-regional (declarado) | banco-gerenciado | `data/precos/api/ibm-databases-for-postgresql-standard-gen2-nao-regional-2026-08-13.json` | 99688 | 13 |
| IBM | `databases-for-mongodb` | `standard-gen2` | não-regional (declarado) | banco-gerenciado | `data/precos/api/ibm-databases-for-mongodb-standard-gen2-nao-regional-2026-08-13.json` | 99694 | 13 |
| IBM | `databases-for-redis` | `standard-gen2` | não-regional (declarado) | banco-gerenciado | `data/precos/api/ibm-databases-for-redis-standard-gen2-nao-regional-2026-08-13.json` | 99333 | 13 |
| IBM | `is.vpc` | `nextgen-egress` | br-sao | egress | `data/precos/api/ibm-is.vpc-nextgen-egress-br-sao-2026-08-13.json` | 19450 | 1 |
| IBM | `databases-for-mysql` | `standard` | br-sao | banco-gerenciado | `data/precos/api/ibm-databases-for-mysql-standard-br-sao-2026-08-13.json` | 84930 | 11 |
| IBM | `databases-for-postgresql` | `standard` | br-sao | banco-gerenciado | `data/precos/api/ibm-databases-for-postgresql-standard-br-sao-2026-08-13.json` | 85089 | 11 |
| IBM | `databases-for-mongodb` | `standard` | br-sao | banco-gerenciado | `data/precos/api/ibm-databases-for-mongodb-standard-br-sao-2026-08-13.json` | 84980 | 11 |
| IBM | `databases-for-redis` | `standard` | br-sao | banco-gerenciado | `data/precos/api/ibm-databases-for-redis-standard-br-sao-2026-08-13.json` | 85058 | 11 |
| AWS | `AmazonEC2` | instâncias de propósito geral e otimizadas para computação, Linux, locação compartilhada, sob demanda; e volumes EBS gp3 | sa-east-1 | compute + bloco | `data/precos/api/aws-AmazonEC2-sa-east-1-2026-08-13.json` | 2361679 | 171 produtos na fatia |
| AWS | `AmazonRDS` | MySQL, PostgreSQL e Oracle (BYOL e Standard Edition Two com licença inclusa), sob demanda | sa-east-1 | banco-gerenciado + licenca | `data/precos/api/aws-AmazonRDS-sa-east-1-2026-08-13.json` | 4638011 | 1122 produtos na fatia |
| AWS | `AmazonElastiCache` | nós Redis sob demanda | sa-east-1 | banco-gerenciado | `data/precos/api/aws-AmazonElastiCache-sa-east-1-2026-08-13.json` | 2065928 | 464 produtos na fatia |
| AWS | `AmazonDocDB` | instâncias sob demanda e armazenamento | sa-east-1 | banco-gerenciado | `data/precos/api/aws-AmazonDocDB-sa-east-1-2026-08-13.json` | 99937 | 50 produtos na fatia |
| AWS | `AmazonEKS` | horas de plano de controle | sa-east-1 | contêineres | `data/precos/api/aws-AmazonEKS-sa-east-1-2026-08-13.json` | 974069 | 703 produtos na fatia |
| AWS | `AWSLambda` | requisições, GB-segundo e concorrência provisionada | sa-east-1 | serverless | `data/precos/api/aws-AWSLambda-sa-east-1-2026-08-13.json` | 534128 | 389 produtos na fatia |
| AWS | `AmazonS3` | armazenamento padrão e requisições | sa-east-1 | objeto | `data/precos/api/aws-AmazonS3-sa-east-1-2026-08-13.json` | 531826 | 377 produtos na fatia |
| AWS | `AWSDataTransfer` | saída para a internet | sa-east-1 | egress | `data/precos/api/aws-AWSDataTransfer-sa-east-1-2026-08-13.json` | 1593364 | 1071 produtos na fatia |
| AWS | `AWSELB` | balanceador de aplicação: horas e unidades de capacidade | sa-east-1 | rede | `data/precos/api/aws-AWSELB-sa-east-1-2026-08-13.json` | 17440 | 12 produtos na fatia |
| AWS | `AmazonBedrock` | inferência por token dos modelos disponíveis | sa-east-1 | ia | `data/precos/api/aws-AmazonBedrock-sa-east-1-2026-08-13.json` | 873357 | 606 produtos na fatia |
| IBM | `ibm-cloud-object-storage-br-sao` | tela de provisionamento | br-sao | objeto | `data/precos/api/ibm-cloud-object-storage-br-sao-2026-08-13.json` | 5879 | 27 |
| IBM | `ibm-cloud-object-storage-us-south` | tela de provisionamento | us-south | objeto | `data/precos/api/ibm-cloud-object-storage-us-south-2026-08-13.json` | 5800 | 27 |

## Alvos selados sem captura em disco

Nenhum. Todos os alvos da lista selada têm corpo cru em disco.

## Segunda classe de evidência (D14, `pagina-publica`)

| Item de custo | Fonte | Itens extraídos | Evidência em disco | SHA-256 |
|---|---|---|---|---|
| `ia` | https://www.ibm.com/products/watsonx-ai/pricing | 47 (22 com unidade) | `data/evidencia/ibm-watsonx-ai-2026-08-13.html` | `53c5e231a7fc7c57…` |
| `objeto` | https://www.ibm.com/products/cloud-object-storage/pricing | 3 (1 com unidade) | `data/evidencia/ibm-cloud-object-storage-2026-08-13.html` | `ee28c0c0843f4819…` |
| `egress` | https://www.ibm.com/products/virtual-private-cloud/pricing | — | **sem captura** | — |
| `banco-gerenciado` | https://www.ibm.com/products/databases-for-postgresql/pricing | 1 (0 com unidade) ⚠️ **sem unidade de cobrança — não é tarifa** | `data/evidencia/ibm-databases-precos-2026-08-13.html` | `abd6ed61af7f30f7…` |

### Itens de custo ainda sem preço por nenhuma via

Nenhum.

### Gate D15 — conjunto mínimo publicável

**PASSA** quanto à existência de preço: todo item dominante tem número em disco.
