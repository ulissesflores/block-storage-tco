# Pre-registration of the analysis plan

> **Status of this file.** It is an English rendering of the pre-registration that was sealed on
> 2026-08-13, in Portuguese, as the `prereg` stage of the provenance chain. The sealed original is
> not redistributed (it belongs to the study's internal record); its SHA-256 is
> `175909c517884b320201455da8ef41dd415b99e6788cddbdc7b87cb228a05698`, 10,895 bytes, and it is the
> single leaf of `stage_prereg` in every run of [`docs/chain-ledger.tsv`](docs/chain-ledger.tsv).
>
> **What the chain proves about the ordering, independently of this text:** in the first run,
> `20260813-pre-captura`, `stage_prereg` is already populated while `stage_data` is `e3b0c442…` —
> the hash of the empty input. The plan was sealed when no price had been captured.

## 1. Why this document exists

The risk it covers has a name: the break condition of the thesis could be chosen **after** seeing
which cloud wins. Kingman's approximation makes waiting time proportional to `ρ/(1−ρ)`; calibrating
utilisation near 0.9 makes any gap explode and near 0.5 makes it vanish. Without a prior commitment,
the author would be deciding whether their own thesis survives by turning a knob that has no source
— and the provenance chain would then seal that choice cryptographically, lending it the appearance
of rigour. Sealing the grid first is what removes the freedom.

## 2. Thesis and break condition

**Thesis.** The total-cost comparison identifies a winning provider only after the sizing method is
fixed. The reproducible spreadsheet quantifies how sensitive the verdict is to the choice between
sizing by specification and sizing by latency target, and measures which cost items dominate the gap
between IBM Cloud and AWS.

**Primary deliverable — the turning point.** Which capacity multiplier over specification-based
sizing makes the verdict change cloud. That number is a function **only of the captured prices and
of each catalogue's SKU ladder** — it is invariant to the assumed workload. The operating point is
an illustration on the curve, never the basis of the result.

**Break condition, over the whole grid rather than at a point.** The thesis is refuted if, with the
captured prices, the difference between the two sizing methods is below 10% of the 36-month total
**in both clouds** and the ranking of cost items stays identical **at every point** of the grid in
section 4. One violating point is enough for the thesis not to be refuted; the whole grid satisfying
it is enough for it to be.

**Reporting commitment.** The result is reported whichever way it comes out. If the thesis is
refuted, the article states the refutation in the body and in the closing section, with the table
that supports it. There is no path in which a null result goes unpublished.

## 3. Demand vector

Sealed in `configs/premissas-carga.json`, which enters the `inputs` stage of the same run. The
values that govern cost — peak and mean requests per second, service time, response size, object
storage and its growth, monthly data transfer out, block growth, backup retention, serverless
invocations and duration — are all there, each with its own justification and stamped as a
**declared assumption**. The cost-model tests lock them as known answers.

**Epistemic boundary, carried verbatim into the article.** The prices are real and captured; the
workload of the company is fictional. Arrival rate, service time and coefficients of variation are
declared assumptions, never telemetry. The honest comparison is the model against the informed
baseline of the case — not against production data, which does not exist.

## 4. Sensitivity grid

Sealed in `configs/premissas-carga.json` under `grade_sensibilidade`:

| Axis | Pre-registered values |
|---|---|
| Target utilisation `ρ` | 0.50 · 0.60 · 0.70 · 0.75 · 0.80 · 0.85 · 0.90 |
| Service coefficient of variation `Cs` | 1.0 · 1.2 · 1.5 · 2.0 |
| Capacity multiplier | 1.00 · 1.25 · 1.50 · 1.75 · 2.00 · 2.50 · 3.00 |

**All** points are reported. Trimming the grid after seeing it is the very vice the grid exists to
prevent.

**Caveat declared before measuring:** a G/G/1 model per instance overstates waiting time relative to
a set of instances sharing one queue. Since the same model applies to both clouds the comparison
does not break — but the caveat goes into the text rather than being left for a reviewer to find.

## 5. Commercial-parity matrix

Sealed in `configs/projeto-tecnico.json` under `paridade_comercial`. Ten dimensions, each with **one**
value equal on both clouds; the primary scenario is always the lowest-commitment one. Comparing IBM
with a commitment discount against AWS on demand would turn the verdict into an artefact of the
discount model, and one sentence from a reviewer would destroy the work.

Sensitivity scenarios named **before** capture: (a) a one-year commitment on both sides; (b) Oracle
licence included, which exists only in the Standard Two edition on AWS.

## 6. Cost taxonomy

Sealed in `configs/projeto-tecnico.json` under `taxonomia_custo`. Ten items: compute, block storage,
object storage, data transfer out, licences, managed-service premium, backup, support, network with
IP and load balancer, and observability. **Every item appears in the spreadsheet either with a number
or with an explicit, justified "not applicable" — never omitted.** The company is e-commerce and
digital content: a comparison without egress and without object storage would have no floor.

## 7. List of SKUs to price

Sealed in `configs/projeto-tecnico.json` under `skus_a_precificar`. The **entire ladder** of the
candidate families is priced and a selection rule derives the SKU for each server: the smallest SKU
of the declared family, available in the region, that satisfies the required vCPU and RAM; ties
broken by the lowest captured price.

Pinning the SKU by hand would allow choosing the winner. Fixing the rule and pricing the ladder makes
the SKU a consequence of the evidence — and the legitimate differentiation between the clouds becomes
each catalogue's capacity rounding, which is captured data.

**Capturing outside this list requires a new seal.** Coverage is checked against this list, never
against a list redefined at capture time.

## 8. Decisions locked before capture

| # | Decision | Content |
|---|---|---|
| **D12** | Currency and billing country | **US dollars, country `USA` on both clouds.** The real appears only in a footnote with a dated exchange rate and enters no total. Verified line by line. Measured reason: the same SKU is served as USD 0.266 and BRL 1.4763 — without the lock a spreadsheet would add the two and pass every check |
| **D13** | Oracle comparison convention | **Bring-your-own-licence symmetrically on both clouds** in the primary scenario — the only convention in which the verdict depends on captured infrastructure rather than on an inference about core counting that the evidence does not support. On the IBM side both paths are priced (virtual machine and bare metal), because the smallest bare metal in São Paulo has 16 cores and that step is a finding, not a choice. Named sensitivity: licence included in the AWS Standard Two edition, which has no IBM equivalent |
| **D14** | Classes of price evidence | **Two, both accepted, both declared per line:** `api-versionada` (AWS offer file by date; three-hop traversal of the IBM catalogue) and `pagina-publica` (public page with the file hashed and dated). Requiring an API for everything would leave object storage, egress and the IBM managed databases with no price at all |
| **D15** | Minimum publishable set | A scenario is publishable only if **all ten** taxonomy items are resolved — with a price and a declared class, or with an explicit and justified "not applicable" — **and** the dominant ones carry a number: compute, block, object, egress, managed database, Oracle compute and the AI layer. A scenario that violates this enters neither the spreadsheet nor the text; the gap is declared as a named limitation |

## 9. Which architecture the latency model describes

The queueing model describes **phase 1**: the REST API application on a compute-optimised virtual
machine behind a load balancer. Phase 2 is serverless by the terms of the case, and the tension with
the sub-200 ms requirement — cold start — is reconciled in the text with the named mitigation
(minimum warm instance, provisioned concurrency) and its cost priced. Without this declaration the
curve would describe the architecture that phase 2 discards.

## 10. Findings already measured that the pre-registration carries

Each of these is a dated fact with a raw body on disk, and none depends on the cost result:

1. **IBM's AI layer is not declared in São Paulo.** In the Global Catalog on 2026-08-13,
   `data-science-experience`, `pm-20`, `aiopenscale` and `lakehouse` declare
   `au-syd, ca-tor, eu-de, eu-gb, jp-tok, us-south` — without `br-sao`. AWS lists `sa-east-1` for
   Bedrock. Graduation: "not declared in the node consulted, with a date", never "does not exist".
2. **The IBM virtual-machine price requires three hops.** The one-hop path returns zero without error.
3. **The IBM managed databases have a plan with a region and no price, and a plan with a price and no
   region.**
4. **IBM Object Storage returns a 404 pricing mapping**, and there is no data-transfer metric on the
   instance price.
5. **The IBM Kubernetes control plane exposes no priced metric; the AWS one is billed per hour.**
6. **The smallest IBM bare-metal server in São Paulo has 16 cores** — twice the Oracle requirement.
7. **Oracle's authorised-cloud policy names AWS, Azure and GCP; IBM does not appear**; and the IBM
   catalogue has no managed Oracle.

## 11. What this pre-registration does not promise

- It does not promise the thesis will survive. It promises to report the entire grid.
- It does not promise a percentile without declaring the regime: the 200 ms target is treated as a
  percentile only under heavy-traffic convergence (Kingman, 1962), with the regime declared; outside
  it, the text speaks of mean waiting time with a declared margin.
- It does not promise price coverage the source does not give: where an API path yields no price, the
  line uses the second evidence class, declared — and where no path yields one, the gap is written up
  as a limitation.
- It does not promise a discrete-event simulation: it was cut, with the reason recorded.

## 12. Outcome, recorded after the fact

The grid was run in full. **The thesis was not refuted:** 8 of the 24 evaluated points violate the
break condition, so the difference between sizing methods is not uniformly below 10%
(`output/tabelas/tese-veredito.csv`). The ranking of clouds, however, never changed — there is **no
turning point inside the pre-registered grid** (`output/tabelas/virada-sintese.csv`), and that
absence is reported as a result, not hidden as a missing one: the SKU ladder is discrete and the
crossing may simply not exist in the declared interval.
