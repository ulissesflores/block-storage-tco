# Methodology

How the prices were captured, how the cost model turns them into a 36-month figure, and which of
the inputs are measured facts rather than declared assumptions. Everything stated here is
executable: the section headings map to files, and the files are in this repository.

## 1. The question

An organisation running twelve on-premises servers — six databases (MySQL ×2, PostgreSQL, MongoDB,
Oracle, Redis) and six applications — migrates to public cloud in two phases: a lift-and-shift with
a security layer, then a modernisation with managed databases, containers, serverless APIs and a
corporate AI layer. Two providers are priced side by side, in the same city, on the same day, in
the same currency: **IBM Cloud `br-sao`** and **AWS `sa-east-1`**.

The question is not which cloud is cheaper in the abstract. It is: **after which methodological
choices does the answer stop moving?** That is what the pre-registration commits to measuring, and
why the sizing method is a variable of the study rather than a background decision.

## 2. Price capture — two paths, both declared per line

Every price in this repository carries an evidence class, declared line by line in
`output/tabelas/precos-unitarios.csv`:

| Class | What it means | Where it applies |
|---|---|---|
| `api-versionada` | fetched from a public API, response body saved verbatim | AWS offer files (versioned by date); IBM Cloud Global Catalog |
| `pagina-publica` | extracted by rule from a public page whose raw HTML is saved and hashed | IBM watsonx.ai and Cloud Object Storage product pages |

### 2.1 The three-hop traversal of the IBM catalogue

The single most consequential mechanical finding of the capture: **in the IBM Cloud Global Catalog,
the price of a virtual machine is not on the plan.** Asking the plan for its pricing returns a
metric whose amount is **zero, with HTTP 200 and no error**. The price lives one level deeper:

```text
service  ->  plan  ->  regional deployment  ->  pricing
```

Measured example, 2026-08-13: `bxf-4x16` in São Paulo is **USD 0.266/h**
(`data/precos/api/ibm-is.instance-bxf-4x16-br-sao-2026-08-13.json`, metric
`part-is.instance-hours-bxf-4x16`), and that number appears only at the third hop. A one-hop capture
would have collected zeros silently and no gate would have caught it — which is why `src/capture_prices.py` refuses to record a metric with a zero or absent
amount (`exigir_metricas`), and why the traversal is pinned by known-answer tests with the measured
vectors (`tests/test_tco.py`).

A second trap, also measured and also encoded: **the children of a plan answer only by identifier**.
Requesting `.../databases-for-mysql/standard/%2A` returns 404, while `.../<plan-id>/%2A` returns the
deployments. Reading that 404 as "there is no regional deployment" is what produced — and later
retracted — the claim that São Paulo had no managed-database price. It has one. The retraction is
recorded in `configs/emenda-01-2026-08-13.json`; amendments are dated and appended, never rewritten.

### 2.2 Currency and billing country, locked before capture

A single captured body carries the same SKU in twenty-nine billing countries and fourteen
currencies. In the file cited above, `part-is.instance-hours-bxf-4x16` is served as **USD 0.266**
for country `USA` and **BRL 1.4763** for country `BRA` — the same hour of the same machine. Without
a lock, a spreadsheet would add dollars to reais and every consistency check would still pass. The
pre-registration fixes **USD, billing country `USA`, both clouds**; a test asserts that no line
escapes it.

### 2.3 What has no public price, stated as such

- **Cloud Object Storage** returns `pricing mapping not available` (404) on the catalogue path; it
  was resolved through the JSON that the public provisioning calculator itself consumes, captured by
  code with `region=br-sao`, and cross-checked against `us-south` to prove the endpoint honours the
  region parameter (São Paulo is ~29% more expensive — a control, never an input).
- **IBM's AI layer** — watsonx.ai Studio, Runtime, governance and data — declares
  `au-syd, ca-tor, eu-de, eu-gb, jp-tok, us-south` in the catalogue node consulted on 2026-08-13.
  **`br-sao` is not among them.** The published statement is "not declared in the node consulted on
  that date", never "does not exist": the provider's regional-availability documentation returned
  HTTP 403 to this client, and that is recorded rather than papered over.

## 3. Sizing — two methods, one of which is derived

**Iso-specification** matches the vCPU and RAM of each existing server, rounding up to the smallest
SKU of the declared family available in the region. The selection *rule* is sealed, not the SKUs:
pinning a SKU by hand would let the author choose the winner, whereas pricing the whole ladder makes
the SKU a consequence of the captured catalogue.

**Iso-SLA** adds capacity headroom where a service-level requirement actually constrains the design
— three of the twelve servers: the transactional MySQL (high availability), the REST API (latency
below 200 ms) and the authentication microservices (high availability and fault tolerance).

The headroom multiplier is **not chosen**. `src/filas.py` applies the Kingman (1961) G/G/1
approximation, and the 95th percentile is read off the heavy-traffic exponential limit
(Kingman, 1962) with the regime declared. The published operating point, ×1.50, is simply the
smallest multiplier in the pre-registered grid whose p95 (166.26 ms) fits the 200 ms target.

> The distinction matters more than it looks. Waiting time grows as `ρ/(1−ρ)`: tuning utilisation
> near 0.9 makes any gap explode, and near 0.5 makes it vanish. An author free to pick the
> utilisation is an author free to decide whether their own thesis survives. Sealing the grid before
> capture, and reporting **every** point of it, is what removes that freedom — see
> [`PREREGISTRATION.md`](PREREGISTRATION.md).

## 4. Cost model

`src/tco.py` computes a monthly cost per configuration and projects it over 36 months at 730 hours
per month. Ten cost items are always present — compute, block storage, object storage, data
transfer out, licences, managed-service premium, backup, support, network/IP/load balancer,
observability — and an item that does not apply is written as an explicit, justified zero rather
than omitted. Four configurations are produced: each cloud, each phase.

Three modelling decisions carry more weight than the rest, and each is declared:

1. **Commercial parity.** Ten dimensions are held equal across the clouds, and the primary scenario
   is always the lowest-commitment one. Comparing a discounted reserved price on one side against
   on-demand on the other would make the verdict an artefact of the discount model.
2. **Oracle.** IBM Cloud has no managed Oracle service, and the smallest bare-metal server in São
   Paulo has 16 cores — twice what the workload needs. The primary scenario therefore uses
   **bring-your-own-licence symmetrically** on both sides, with the bare-metal path priced as a
   declared sensitivity rather than folded into the headline.
3. **Egress is two prices, not one.** Data leaving Object Storage is billed on its own tariff
   (0.1935 USD/GB in the first tier) and is **not** the VPC egress price (0.115197 USD/GB). Five of
   the six monthly terabytes are media served from object storage; modelling all six at the VPC rate
   would understate IBM's egress. A test locks the fact that the two prices are distinct.
4. **Managed databases are billed per cluster member.** The captured node prices *per host*, and the
   IBM Cloud Standard plan provisions three data members for MySQL and MongoDB and two for
   PostgreSQL and Redis; disk follows the multiplier each product page declares, which for MongoDB
   is **two** even though the member count is three. Backup on those services is zero by the
   documented allowance — backup storage equal to the total disk provisioned, at no cost — the same
   treatment the AWS side receives. Counts, multipliers, the allowance and the SHA-256 of every
   source page live in [`configs/emenda-07-2026-08-16.json`](configs/emenda-07-2026-08-16.json);
   the pages themselves are the provider's text and are not redistributed here. The modelled backup
   volume is **one full copy** on both sides, not the provider default of one daily copy retained
   for thirty days, so that line is a floor rather than a central estimate.

## 5. What is measured, what is informed, what is generated

| Nature | In this study | What may be asserted from it |
|---|---|---|
| **Measured** | the public prices of both providers, with the request path, the date and the raw body | verifiable fact; carries the cost comparison |
| **Informed** | the twelve-server specification of the case | premise of the case; it is the iso-specification baseline |
| **Generated** | the synthetic workload and the queueing output | illustrative; it is **not** telemetry of any real system |

The only real-world data in this work is the **price**. The company is fictional and no production
telemetry exists, so the honest comparison is model against the informed baseline — never model
against "real usage". Writing it any other way would be the over-claim a reviewer should attack.

## 6. Determinism and tests

`run_all.py` rebuilds the results from the frozen bodies, runs the tests, and then verifies the
checksums; a non-deterministic step would fail that last check. The tests are not smoke tests: they
pin the published totals, the tariff traversal with measured vectors, the currency separation, the
distinctness of the two egress prices, the Kingman known answers (including the case where the
closed form must stay exact for M/M/1), the refusal to return a number for an unstable queue, and
every headline number printed in the README.

## 7. Known limitations

- A **G/G/1 model per instance overstates waiting time** relative to a pool sharing a single queue.
  The same model is applied to both providers, so the comparison holds; the caveat is stated here
  rather than left for a reader to discover.
- The IBM `/pricing` endpoint is **not versioned by date**. A capture made today cannot be compared
  byte for byte with 2026-08-13, which is exactly why the bodies are frozen and hashed.
- Tier semantics for IBM egress are labelled "Graduated Tier (Step Tier)", two schemes that bill
  differently. The sealed demand vector (6 TB/month) sits far below the first tier ceiling
  (10,000 GB), so both readings give the same price. Should a sensitivity push the volume past that
  ceiling, the ambiguity becomes material again and needs a primary source before any number is
  published.
- Availability of a service is reported as **declared in the node consulted, with a date** — never
  as existence or non-existence.
