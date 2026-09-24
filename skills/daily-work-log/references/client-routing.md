# Client Routing Table

Source of truth for attributing daily activity to a client. Match an item to a client when ANY signal hits: the email domain, a store/alias name, a key person, the project code, or the website domain. An item can map to more than one client. If nothing matches, route to **Internal / DigitalCLIQ** or **Personal**.

Keep this table in sync with `Projects/*/README.md` frontmatter. Codes are the folder names under `Projects/`.

| Code | Client | Store / aliases | Email + web domains | Key people | Brand / vertical |
|---|---|---|---|---|---|
| MCP | McPeek Chrysler Dodge RAM of Anaheim | McPeek, McPeek's, McPeeks, Anaheim CDJR | mcpeekcdjr.com, mcpeeks.com | Stewart Benjamin (GM), Paul Lewis (Service), Frank (finance/compliance), Eddie Vidauri (sales), Tyler Wafa (sales), Josh Jellerson | Automotive (CDJR / RAM) |
| NCBMW | New Century BMW | New Century, NCBMW, New Century Auto Group | newcenturybmw.com, newcenturyautogroup.com, newcenturyautos.com | Frank Lin (owner), Lennie (GSM), Dan, Sharon Wilhort | Automotive (BMW) |
| SBMW | Sterling BMW | Sterling | sterlingbmw.com | Bob/Robert Wieland (service), Conrad, Wes, Eric D | Automotive (BMW) |
| NOI | Nissan of Irvine | Nissan Irvine, NOI | nissanofirvine.com | Ron Campbell (GM/co-owner), Darlene Salazar | Automotive (Nissan) |
| CDHD | Chuck Deluxe Harley-Davidson | Chuck Deluxe, CDHD | chuckdeluxe.com | Maria | Powersports (Harley-Davidson) |
| CHC | Covina Hills Chevy | Covina Hills, CHC | (confirm) | (confirm) | Automotive (Chevrolet) |
| Atlas | Atlas Shippers International | Atlas, Atlas Shippers | atlasshippers.com | Marketing team | Logistics / balikbayan boxes |
| KCC | Kasama Coffee Collective | Kasama, Kasama Coffee | (confirm) | (confirm) | Coffee / food service |
| CCT | Cactus Craft | Cactus Craft | (confirm) | (confirm) | TBD |
| DKD | DK's Donuts | DK's, DK Donuts | (confirm) | (confirm) | Food service |
| MFK | Modern Filipino Kitchen | MFK | (confirm) | (confirm) | Food service |
| RAVE | Rave Dance Studio | Rave | (confirm) | (confirm) | Local services (dance) |
| TGN | The Geekish Network | Geekish, TGN | (confirm) | (confirm) | Media / network |
| FFLOW | Finance Flow (prospect) | Finance Flow, Privecho | privecho.com | Founder-led | SaaS / privacy finance app |
| PAG | Penske Automotive Group (prospect) | Penske, PAG, Crevier | penskeautomotive.com | Anthony La (ALa) | Automotive dealer group |
| AI-Training-Program | DigitalCLIQ AI Training Program | GM AI Training, AI training book | (internal) | Drew, dealership GMs | Internal product |
| Roundel-Cup | Roundel Cup (concept) | Roundel Cup | (internal) | Drew | Concept / event |

## Non-client buckets

- **Internal / DigitalCLIQ**: agency operations, the vault/skills, DigitalCLIQ's own social, hiring/recruiter replies, tooling (SEMrush account-level, Gmail cleanup, scheduling).
- **Personal**: family, Krystal, Olive, golf, errands, anything not work. Keep it light and never route personal content into a client file.

## Routing rules

1. Prefer the strongest signal: email to/from a client domain, or an explicit store name, beats a loose first-name match (many "Frank"s exist: Frank at MCP vs Frank Lin at NCBMW. Disambiguate by domain or context).
2. Vendors and OEM contacts attach to the client they serve, not their own company. Examples: Lamar (drivas@lamar.com, rbondar@lamar.com) and Shift Digital (rbrowning@shiftdigital.com) → whichever dealer the work was for (MCP for the billboard slides, SBMW for the BMW Heavy Up). BMW NA contacts (bmwna.com: Adam Neumann, Ed McRae) → the specific BMW store in context, else Internal.
3. If an item clearly spans two clients, log it under both.
4. When unsure, route to Internal / DigitalCLIQ and flag it in the daily note rather than guessing a client.
