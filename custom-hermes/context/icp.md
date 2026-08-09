# Ideal Customer Profile (ICP)

## Purpose

This document defines the companies and decision-makers that the Sales Agent should identify, research, qualify, score, and prepare for outreach.

The agent MUST apply the hard filters before calculating a lead score.

---

## Hard filters

A lead that fails any hard filter must be **REJECTED** and must not receive a score.

### Industry

Target companies operating in:

* Healthcare and healthcare services
* Pharmaceuticals and life sciences
* Education and EdTech
* Manufacturing
* Engineering and construction
* Real estate and property services
* Logistics and transportation
* Retail and e-commerce
* Professional services
* Financial and business services
* SaaS and technology companies
* Marketing and media companies
* Hospitality and travel
* Other businesses with clear software, automation, CRM, data, or AI requirements

Adjacent industries may be considered when a clear technology requirement or business pain is visible.

### Location

Primary target:

* India

Priority regions:

* Tamil Nadu
* Karnataka
* Telangana
* Maharashtra
* Kerala
* Andhra Pradesh
* Delhi NCR
* Gujarat
* Uttar Pradesh

Secondary target markets:

* United Arab Emirates
* United States
* United Kingdom
* Singapore
* Australia

The agent must respect the requested geography when the user specifies a different target market.

### Company size

Preferred:

* 10-500 employees

Priority:

* 20-250 employees

Smaller companies may qualify when there is a clear technology project, active hiring, expansion, or automation requirement.

Larger companies may qualify when a specific department, business unit, or technology requirement can be identified.

### Must have

A qualified company should have:

* A legitimate public website
* A clearly identifiable business
* Publicly available company information
* A business use case that could benefit from software, AI, automation, CRM, web/mobile applications, cloud, or digital transformation
* At least one identifiable business or technology decision-maker when possible

### Exclude

Reject:

* Direct competitors when identified
* Companies already present in the CRM
* Duplicate companies
* Fake or suspicious businesses
* Companies without a legitimate public presence
* Government organizations unless explicitly requested
* Political organizations
* Non-business organizations unless explicitly requested
* Companies with no identifiable business relevance
* Leads based only on scraped or unverifiable claims
* Companies where the available information is clearly outdated or unreliable

Do not reject a company solely because it has no public email address. A qualified company can still be stored if other useful public information exists.

---

# Scoring dimensions

Total score: **100 points**

| Dimension            | Weight | Scoring                                                                                                                                              |
| -------------------- | -----: | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Industry fit         |     25 | Exact target industry = 25; adjacent industry = 10-20; weak fit = 0-5                                                                                |
| Size fit             |     20 | Ideal 20-250 employees = 20; 10-19 or 251-500 = 10; outside preferred range = 0-5                                                                    |
| Pain signals visible |     25 | Strong evidence of a problem RedMind can solve = 20-25; moderate evidence = 10-19; weak/no evidence = 0-9                                            |
| Reachability         |     15 | Named decision-maker + verified business email = 15; named decision-maker + public contact = 10; generic business contact = 5; no usable contact = 0 |
| Buying signals       |     15 | Strong recent buying/expansion signal = 12-15; moderate signal = 6-11; weak/no signal = 0-5                                                          |

---

## Industry fit — 25 points

### 25 points

Company is directly within a priority vertical and has a technology-related business requirement.

Examples:

* Healthcare company requiring CRM automation
* Manufacturing company requiring an internal ERP/workflow system
* Education company requiring LMS development
* Logistics company requiring tracking/automation
* SaaS company requiring a custom application or AI integration

### 10-20 points

Adjacent industry with a clearly identified technology requirement.

### 0-5 points

No meaningful connection between the company's business and RedMind's services.

---

## Size fit — 20 points

### 20 points

10-250 employees with a clear technology or business-process requirement.

### 10 points

251-500 employees or very small company with strong buying signals.

### 0-5 points

Company size is significantly outside the target range and there is no strong justification.

---

## Pain signals visible — 25 points

Look for publicly available evidence such as:

* Hiring developers or technology teams
* Hiring CRM/ERP specialists
* Hiring automation or AI roles
* Outdated website or digital experience
* Manual business processes
* Multiple disconnected systems
* Need for CRM implementation
* Need for customer-management automation
* Need for mobile applications
* Need for web application development
* Need for internal dashboards
* Need for data/reporting automation
* AI adoption initiatives
* Digital transformation initiatives
* Technology migration
* Cloud migration
* Customer support automation
* Sales process problems
* Operations/process inefficiencies
* Recent technology-related project announcements

The agent must provide the actual public evidence behind a pain signal.

Never invent a pain point merely because the company belongs to the target industry.

---

## Reachability — 15 points

### 15 points

Named decision-maker with a verified business email.

### 10 points

Named decision-maker with a public professional profile or other reliable business contact.

### 5 points

Only a generic business contact such as:

* info@
* sales@
* contact@
* support@

### 0 points

No usable public contact information.

The agent must never fabricate or guess an email address.

---

## Buying signals — 15 points

Look for recent signals such as:

* New funding
* Business expansion
* New branch/location
* New product launch
* New market entry
* Rapid hiring
* Technology hiring
* Leadership change
* Rebranding
* Digital transformation initiative
* New website/application launch
* New partnership
* Acquisition
* Business growth
* New customer-facing platform
* Public request for software/technology services

Recent signals should receive more points than old signals.

---

# Tier thresholds

## Hot

Score: **70-100**

Requirements:

* Score >= 70
* Named decision-maker identified
* At least one meaningful business/pain/buying signal

Action:

* Prioritize for sales research
* Prepare personalized outreach
* Put outreach draft into `outbox/`
* **Never send without human approval**

---

## Warm

Score: **45-69**

Requirements:

* Meets hard filters
* Reasonable business fit
* Some evidence of potential need

Action:

* Store in CRM
* Continue research when useful
* Prepare outreach only when sufficient evidence exists
* Do not prioritize over Hot leads

---

## Cold

Score: **0-44**

Action:

* Store in CRM if useful
* Do not create outreach
* Do not send messages
* Reconsider only if new qualifying information appears

---

# Decision-maker roles

Prioritize decision-makers in this order:

### Primary

* Founder
* Co-Founder
* CEO
* Managing Director
* Owner
* Director
* CTO
* CIO
* COO
* Head of Technology
* Head of IT
* Head of Operations

### Secondary

* VP Technology
* IT Manager
* Technology Manager
* Operations Manager
* Digital Transformation Head
* Product Head
* Head of Digital
* Head of Sales
* Sales Director
* Marketing Director
* CRM Manager

### Project-specific

For education:

* Founder
* Director
* Academic Director
* Operations Head
* Technology Head

For healthcare:

* Founder
* Hospital Director
* Operations Head
* IT Head
* Digital Transformation Head

For manufacturing:

* Managing Director
* Plant Head
* Operations Head
* IT Head
* Digital Transformation Head

For real estate:

* Founder
* Managing Director
* Operations Head
* Sales Head
* CRM Head
* Technology Head

The agent should prefer the person who can influence or approve a technology purchase rather than simply selecting the most senior person available.

---

# Search geography & language

## Primary geography

India

## Priority states

* Tamil Nadu
* Karnataka
* Telangana
* Maharashtra
* Kerala
* Andhra Pradesh
* Delhi NCR
* Gujarat
* Uttar Pradesh

## Secondary markets

* UAE
* USA
* UK
* Singapore
* Australia

## Language

Primary:

* English

The agent should search public sources using English queries unless the user specifies another language.

When researching Indian companies, include relevant city, state, industry, and decision-maker terms in search queries.

---

# Lead research requirements

For every qualified lead, attempt to collect:

* Company name
* Website
* Industry
* Location
* Company size
* Company description
* Public business phone
* Public business email
* Decision-maker name
* Decision-maker designation
* Public professional/profile URL
* Relevant technology information
* Pain signal
* Buying signal
* Source URLs
* Qualification reason
* Score
* Tier
* Recommended sales approach

All important claims must have a reliable public source.

---

# Data integrity rules

The Sales Agent MUST:

* Use public information only
* Never fabricate company information
* Never fabricate contact information
* Never guess email addresses
* Never claim an email is verified when it has not been verified
* Distinguish between discovered, verified, and inferred information
* Record source URLs for important findings
* Deduplicate against the CRM before creating a new lead
* Respect company/contact opt-outs
* Never send outreach automatically
* Place outbound messages into the approval outbox first

---

# Lead qualification principle

The agent should not ask:

> "Can we sell software to this company?"

Instead, it should determine:

> "Is there public evidence that this company has a business problem or initiative that RedMind's technology services could reasonably address?"

Only evidence-based opportunities should receive high scores.
