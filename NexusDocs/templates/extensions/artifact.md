# Extension-to-10-days template contract

## Reference authority

- Authoritative source: `F:\\продления\\продление Шмелёв В.Ю.docx`
- SHA-256: `DF309D7AE0C00A783FEA659B7840652765E03953B7A1EB544FF64B2E4DB90A05`
- The source is a clean, final three-page example supplied by the user.
- The separately annotated copy is used only to identify variable values; its extra inline annotations and pagination are not part of the output.

## Document structure and layout

- A4 portrait throughout, five Word sections, three visible pages.
- Page 1: approval block, centered plan title, five-row action table, document date and investigator signature.
- Page 2: approval block and motivated motion to extend the verification period.
- Page 3: instructions concerning execution and reporting.
- Preserve the original section breaks, margins, paragraph spacing, tab stops, table geometry, borders, headers, footers, and signature positions.
- The source uses Times New Roman with direct formatting. Preserve source typography and local emphasis.
- No additional titles, branding, headers, footers, page numbers, highlights, comments, fields, drawings, or content controls may be introduced.

## Variable slots

- Person: full name in the grammatical forms used by the sentence, initials, birth date where present.
- Military: unit number without a duplicated `в/ч` prefix, rank and its genitive form, position, unit deployment.
- Service basis: exactly one of `по контракту` or `по мобилизации`.
- SOCH: date, circumstance sentence, article.
- Registration date: the date the report was registered.
- Three-day document date: registration date plus two calendar days.
- Ten-day deadline: registration date plus nine calendar days.
- The article value must be consistent on all three pages, including the instructions page.

## Fixed content

- Keep the named officials, department names, addresses, legal citations, request list, performer, and signature captions from the clean reference unchanged unless they are explicitly declared as variable slots above.
- Keep the five plan actions and their order unchanged.

## Conditional and validation rules

- `Неявка в срок` and `Самовольное оставление части` are the only supported circumstance choices.
- Do not emit any clock time or placeholder time wording such as `Около 00 часов 00 минут` or `Около 15 часов 00 минут`.
- Existing people may have empty newly added fields. In that case generation must stop before writing a document and the UI must instruct the user to complete the fields through `Редактировать`.
- Generated output must remain a three-page editable DOCX matching the reference layout as closely as variable text permits.
