# NFIP Data Dictionary (verified)

Field names and code values below were pulled from FEMA's own metadata API
(`/api/open/v1/OpenFemaDataSetFields`) on 2026-09-28, not from a blog post or
a third-party mirror. If a column name here does not match the file you
download, FEMA changed the schema - re-run `src/fetch_schema.py`.

## Datasets used

| Dataset | Version | Records | Last refresh | Bulk file |
|---|---|---|---|---|
| NfipClaims | 3 | 2,725,989 | 2026-08-04 | `NfipClaimsV3.parquet` |
| NfipPolicies | 3 | 74,739,461 | 2026-07-27 | `NfipPoliciesV3.parquet` |
| NfipMultipleLossProperties | 1 | 240,651 | 2026-08-04 | `NfipMultipleLossProperties.parquet` |

Base URL for v3 bulk files:
`https://www.fema.gov/about/reports-and-data/openfema/v3/`

## Claims - fields this project uses

Money (all USD):
- `amountPaidOnBuildingClaim`, `amountPaidOnContentsClaim`,
  `amountPaidOnIncreasedCostOfComplianceClaim` - gross paid
- `netBuildingPaymentAmount`, `netContentsPaymentAmount`, `netIccPaymentAmount` - net of recovery
- `buildingDamageAmount`, `contentsDamageAmount` - assessed damage
- `totalBuildingInsuranceCoverage`, `totalContentsInsuranceCoverage` - coverage limits
- `buildingReplacementCost`, `buildingPropertyValue`
- `totalSalvageRecovery`, `totalSubrogationRecovery`

Dates:
- `dateOfLoss`, `openDate`, `mostRecentPaymentDate`, `mostRecentRecoveryDate`
- `yearOfLoss`, `originalConstructionDate`, `asOfDate`

Segmentation:
- `state`, `countyCode`, `reportedZipCode`, `censusGeoid`, `nfipCommunityName`
- `ratedFloodZone`, `floodZoneCurrent`, `occupancyType`, `foundationType`
- `preFirmIndicator`, `postFIRMConstructionIndicator`, `primaryResidenceIndicator`
- `floodEvent`, `causeOfDamage`, `waterDepth`, `crsClassCode`

Non-payment:
- `nonPaymentReasonBuilding`, `nonPaymentReasonContents`

## Policies - fields this project uses

- `totalInsurancePremiumOfThePolicy`, `policyCost`, `fullRiskPremium` - premium
- `policyEffectiveDate`, `policyTerminationDate`, `policyCount`, `policyTermIndicator`
- `propertyState`, `ratedFloodZone`, `floodZoneCurrent`, `occupancyType`
- `totalBuildingInsuranceCoverage`, `totalContentsInsuranceCoverage`
- `rateMethod`, `subsidizedRateType`, `preFIRMConstructionIndicator`, `crsClassCode`

Note the state column differs between the two datasets: claims use `state`,
policies use `propertyState`.

## Code lookups (verbatim from FEMA field descriptions)

### occupancyType
Two-digit codes are Risk Rating 2.0 era. Both generations appear in the same
column, so any grouping must handle both.
```
1  single family residence
2  2-4 unit residential building
3  residential building with more than 4 units
4  non-residential building
6  non-residential - business
11 single-family residential (not mobile home, not a unit in a multi-unit building)
12 residential non-condo building, 2-4 units, all units insured
13 residential non-condo building, 5+ units, all units insured
14 residential mobile/manufactured home
15 residential condo association, one or more units
16 single residential unit within a multi-unit building
17 non-residential mobile/manufactured home
18 non-residential building
19 non-residential unit within a multi-unit building
```

### causeOfDamage
**Warning: this field is multi-valued.** FEMA's own documentation states more
than one cause code can be selected on a single claim, so real values include
combinations such as `2D`. A naive `GROUP BY causeOfDamage` returns
combination strings, not categories. To analyse it properly, split the string
into individual characters and unnest.

Codes 7 and 8 are only valid for losses before 23 September 1995, per the
Upton Jones Amendment.
```
0 other causes
1 tidal water overflow
2 stream, river, or lake overflow
3 alluvial fan overflow
4 accumulation of rainfall or snowmelt
7 erosion-demolition          (pre-1995-09-23 only)
8 erosion-removal             (pre-1995-09-23 only)
9 earth movement, landslide, land subsidence, sinkholes
A closed basin lake
B expedited claim handling, no site inspection
C expedited claim handling, follow-up site inspection
D expedited claim handling, remote adjustment pilot
```

### ratedFloodZone / floodZoneCurrent
Special Flood Hazard Area (SFHA) zones begin with A or V.
```
A            special flood, no base flood elevation on FIRM
AE, A1-A30   special flood, with base flood elevation
A99          special flood with protection zone
AH, AHB      special flood, shallow ponding
AO, AOB      special flood, sheet flow
V            velocity flood, no base flood elevation
VE, V1-V30   velocity flood, with base flood elevation
B, X         moderate flood risk
C, X         minimal flood risk
D            possible flood, undetermined
```

### basementEnclosureCrawlspaceType
```
0 none
1 finished basement/enclosure
2 unfinished basement/enclosure
3 crawlspace
4 subgrade crawlspace
```

### foundationType
```
1 slab
2 basement
3 crawlspace
4 elevated without enclosure (post, pile or pier)
5 elevated with enclosure (post, pile or pier)
6 elevated with enclosure (not post, pile or pier)
```

### buildingDeductibleCode
```
0 $500      1 $1,000    2 $2,000    3 $3,000    4 $4,000
5 $5,000    9 $750      A $10,000   B $15,000   C $20,000
D $25,000   E $50,000   F $1,250    G $1,500    H $200 (group policies only)
```

### condominiumCoverageTypeCode
```
N not a condominium
U individual condo unit insured by unit owner or association
A condominium association
H condo master policy (RCBAP) high-rise
L condo master policy (RCBAP) low-rise
```

### replacementCostBasis
```
R replacement cost basis
A actual cash value basis
```

### nonPaymentReasonBuilding / nonPaymentReasonContents
Complete list. Note 98 and 99 are administrative corrections, not real
declined claims - the pipeline flags them as `is_error_record` and excludes
them from every aggregate.
```
01 claim denied, less than deductible
02 seepage
03 backup of drains
04 shrubs not covered
05 sea wall
06 not actual flood
07 loss in progress
08 failure to pursue claim
09 debris removal only
10 fire
11 fence damage
12 hydrostatic pressure
13 drainage clogged
14 boat piers
15 not insured, damage before policy inception
16 not insured, wind damage
17 erosion type outside flood definition
18 landslide
19 mudflow type outside flood definition
20 no demonstrable damage
97 other
98 error - delete claim (no assignment)     <- administrative, exclude
99 erroneous assignment                     <- administrative, exclude
```

### rateMethod (policies)
```
1 manual          2 specific        3 alternative
4 V-zone risk factor rating form    5 underinsured condo master policy
6 provisional     7 preferred risk policy (non-SFHA)
8 tentative       9 MPPP policy
A optional post-1981 V zone         B pre-FIRM with elevation rating
E FEMA pre-FIRM special rates       F leased federal property
G group flood insurance policy      I incomplete data provisional
P preferred risk policy
```

### locationOfContents
```
1 basement/enclosure/crawlspace/subgrade crawlspace only
2 basement/enclosure/crawlspace/subgrade crawlspace and above
3 lowest floor only above ground level (no basement/enclosure/crawlspace)
4 lowest floor above ground level and higher floors (no basement/enclosure)
5 above ground level, more than one full floor
6 manufactured (mobile) home or travel trailer on foundation
7 enclosure/crawlspace and above
```

### floodCharacteristicsIndicator
```
1 velocity flow
2 low-velocity flow or ponding
3 wave action
4 mudflow
5 erosion
```

### elevationCertificateIndicator
An empty value means not reported, NOT that the property lacks a certificate.
```
1 no EC, original effective date before 1982-10-01, no coverage break
2 no EC, original effective date on/after 1982-10-01, no coverage break
3 EC with base flood elevation
4 EC without base flood elevation
A basement or subgrade crawlspace
B fill or crawlspace
C piles, piers or columns with enclosure
D piles, piers or columns without enclosure
E slab on grade
```

### buildingDescriptionCode
```
01 main house              02 detached guest house    03 detached garage
04 agricultural building   05 warehouse               06 pool/club/rec building
07 tool/storage shed       08 other                   09 barn
10 apartment building      11 apartment unit          12 cooperative building
13 cooperative unit        14 commercial building     15 condominium (whole)
16 condominium unit        17 house of worship        18 manufactured home
19 travel trailer          20 townhouse/rowhouse
```

### disasterAssistanceCoverageRequired
Which federal agency required flood insurance as a condition of disaster aid.
```
0 not required   1 SBA   2 FEMA   4 HHS (cancelled 2009-10-01)   5 other agency
```
