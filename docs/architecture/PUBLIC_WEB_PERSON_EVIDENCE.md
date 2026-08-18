# Public Web Person Evidence — design sketch

**Status:** exploratory architecture based on real-person web research samples  
**Scope:** public, non-scholarly / semi-scholarly web evidence about researchers

## 1. Purpose

Paperazzi already has structured scholarly sources (Zotero, WoS, PDF fallback). This layer serves a different purpose: capture **public web evidence about the people around the papers** — academic genealogy, lab/group membership, event appearances, public photographs, interviews, organizational service, publicly documented personal relationships, and other social context that helps a reader understand a researcher's professional and social network.

This is intentionally not a conventional bibliographic metadata source.

Typical questions include:

- Who trained this researcher, and at which career stage?
- Which groups, centers, committees, workshops, conferences or seminar circuits do they repeatedly appear in?
- Who is publicly documented as a student, postdoc, group alumnus, co-advisor, mentor, spouse/partner, organizer, or recurring collaborator?
- What public portraits, group photographs, conference photographs, interviews, videos or institutional news items exist?
- What non-paper events form a useful timeline of the person?

## 2. Core model: evidence graph, not profile scraping

Do not flatten everything into a single mutable `person_profile`.

```text
Web source page / media asset
          ↓
      observation
          ↓
       assertion
          ↓
 Person ─ relation ─ Person / Organization / Event / Media
```

Every relationship or event must retain the evidence page that supports it.

A page saying two people attended the same conference creates two event-participation assertions. It does **not** automatically create a collaboration, friendship, mentorship, or close-association edge.

## 3. Recommended collectable entity types

### PERSON

Researchers, mentors, students, postdocs, administrators, interviewers, conference organizers and other publicly named people.

### ORGANIZATION

University, department, laboratory, research center, society, committee, company, institute, conference series.

### EVENT

Conference, workshop, seminar, public lecture, award ceremony, institutional meeting, group outing, interview, panel, school, public ceremony.

### MEDIA_ASSET

Portrait, group photo, event photo, video, interview recording, podcast, slide deck. Prefer saving source URL and media URL rather than copying copyrighted media into the repository.

### WEB_PRESENCE

Official faculty profile, group/lab site, institutional biography, society profile, conference speaker page, public professional social account, personal academic website.

## 4. Recommended relationship/assertion vocabulary

### Academic genealogy

- `ACADEMIC_ADVISOR`
- `JOINT_TRAINING_ADVISOR`
- `POSTDOC_ADVISOR`
- `MENTOR`
- `CO_ADVISOR`
- `SUPERVISES`
- `GROUP_MEMBER`
- `GROUP_ALUMNUS`

Do not infer these solely from co-authorship. A paper is evidence of collaboration, not of supervision.

### Institutional / organizational

- `AFFILIATED_WITH`
- `MEMBER_OF_CENTER`
- `COMMITTEE_MEMBER`
- `LEADERSHIP_ROLE`
- `FOUNDER_OF`
- `DIRECTOR_OF`

### Public event participation

Do not create person-person edges first. Store participation:

```text
Person A --SPEAKER_AT--> Event X
Person B --SESSION_CHAIR_AT--> Event X
Person C --ORGANIZER_OF--> Event X
```

Possible roles:

- `SPEAKER_AT`
- `INVITED_SPEAKER_AT`
- `SESSION_CHAIR_AT`
- `ORGANIZER_OF`
- `HOST_OF`
- `PANELIST_AT`
- `ATTENDED`
- `INTERVIEWEE_IN`
- `AWARD_RECIPIENT_AT`

From this graph Paperazzi may derive `CO_PRESENT_AT`, but it must be labeled **derived**, not factual personal closeness.

### Public personal relationships

These can be useful for a social portrait but require a higher evidence threshold:

- `SPOUSE`
- `PARTNER`
- other relationship types only when the people themselves or a reputable institutional/public source explicitly states them.

Do not collect family details from people-search/data-broker sites, leaked sources, home-address databases, or similar sources. Do not infer relationships from shared surnames, photographs, or co-residence claims.

### Collaboration / community

- `PUBLICLY_DESCRIBED_COLLABORATOR`
- `CO_FOUNDER`
- `RECURRING_PROGRAM_PARTICIPANT`

Use ordinary scholarly co-authorship from WoS/Paperazzi for paper-based collaboration; this web layer should capture relationships that are explicitly described outside the publication graph.

## 5. High-value data fields

Each assertion should support:

```text
assertion_id
subject_person_key
predicate
object_type
object_key / object_label
start_date nullable
end_date nullable
as_of_date nullable
place nullable
role_detail nullable
source_id
confidence
assertion_status
visibility_class
notes
```

Suggested status:

```text
SUPPORTED_EXPLICIT
SUPPORTED_CONTEXTUAL
CANDIDATE_NEEDS_REVIEW
CONFLICTING
RETRACTED
```

For production display, prefer `SUPPORTED_EXPLICIT`.

## 6. Web source observation fields

```text
source_id
source_url
source_title
publisher_or_host
source_kind
observed_at
published_at nullable
content_sha256 future
archived_url future
raw_excerpt / evidence_summary
source_quality
```

Useful `source_kind` values:

```text
OFFICIAL_PROFILE
OFFICIAL_GROUP_SITE
INSTITUTION_NEWS
SOCIETY_PROFILE
CONFERENCE_PROGRAM
EVENT_NEWS
INTERVIEW
AWARD_PAGE
PUBLIC_PROFESSIONAL_SOCIAL
MEDIA_PAGE
OTHER_PUBLIC_WEB
```

Source quality should be explicit. Institutional pages, the person's own group site and conference organizers rank above aggregator biographies.

## 7. Media model

A public photo is not merely decoration; it can also be evidence of an event/group snapshot. Store:

```text
media_id
media_type = PORTRAIT | GROUP_PHOTO | EVENT_PHOTO | VIDEO | INTERVIEW_MEDIA
source_page_url
asset_url nullable
caption
captured_or_published_date nullable
people_explicitly_named[]
event_key nullable
copyright_status = UNKNOWN | SOURCE_STATES_LICENSE | PUBLIC_DOMAIN
storage_policy = LINK_ONLY by default
```

Paperazzi should normally hot-link only at research/review time and later proxy/cache only when licensing and product policy permit. The repository sample therefore stores URLs and captions, not copied image files.

## 8. Event graph is especially valuable

Conference and institutional-event records are a rich social layer because they produce many weak-but-explainable connections without pretending that every co-attendee is a collaborator.

Recommended event fields:

```text
event_key
title
event_type
start_date
end_date
venue
city
country
organizer
source_url
participants[]
media[]
```

Repeated co-participation can later support derived features such as:

- same seminar circuit;
- recurring conference community;
- organizer/speaker relationship;
- mentor and trainee appearing together after the trainee becomes independent;
- institutional-network proximity.

## 9. Timeline items worth collecting

Beyond normal CV data:

- advisor changes across BSc/PhD/joint training/postdoc stages;
- public group membership and alumni transitions;
- center/lab formation and leadership;
- committee and professional-society service;
- teaching roles when publicly listed;
- conference talks, session-chair roles, organizing roles;
- visits and visiting-scientist programs;
- interviews and public comments;
- awards and award ceremonies;
- laboratory/group outings and group photographs;
- publicly announced collaborations or center partnerships.

## 10. What should NOT be automatically collected

Even if discoverable on the internet, the following should be excluded from the normal Paperazzi public-person pipeline:

- home address;
- personal/private phone numbers not published as an institutional contact;
- relatives/children from people-search databases;
- private e-mail addresses from data brokers or breaches;
- precise real-time location or travel tracking;
- rumors, anonymous allegations, forum gossip presented as fact;
- inferred romantic/family relationships;
- political/religious/health or other sensitive personal traits unless the researcher explicitly makes them part of a relevant public professional biography and the user deliberately requests that category.

The goal is a rich public social/professional portrait, not surveillance.

## 11. Separation from scholarly facts

The data layer should distinguish:

```text
SCHOLARLY_FACT       WoS/Zotero/publisher/publication evidence
PUBLIC_WEB_FACT      explicit public non-paper evidence
DERIVED_RELATION     computed from facts/events
AI_INTERPRETATION    narrative synthesis
```

Examples:

```text
PUBLIC_WEB_FACT:
Ganglong Cui --ACADEMIC_ADVISOR--> Weihai Fang

PUBLIC_WEB_FACT:
Martin Head-Gordon --SPOUSE--> Teresa Head-Gordon

PUBLIC_WEB_FACT:
Martin Head-Gordon --ORGANIZER_OF--> Northern California Theoretical Chemistry Meeting 2019

DERIVED_RELATION:
A and B appeared at 5 of the same conference-series events between 2019–2025

AI_INTERPRETATION:
A appears embedded in the same recurring theoretical-chemistry community as B
```

The final statement must never be stored as though it were the first kind of fact.

## 12. Initial sample records

Two manually researched sample records are stored at:

```text
examples/public_web_people/ganglong_cui.json
examples/public_web_people/martin_head_gordon.json
```

They are intentionally evidence-heavy and incomplete. Their purpose is to determine the data contract before building an automated storage/import pipeline.
