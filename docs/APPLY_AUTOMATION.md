# Application preparation

## Studio

Each job opens to four tabs.

- **Opportunity:** original text, Greek gist, location evidence, pay if published, dates, source, versions, blockers, AI policy.
- **Match:** every detected requirement with strong, transferable, weak, absent or unknown, and the evidence behind it.
- **Documents:** Tiptap editor for the CV and cover letter, with bold, italic, underline, colour, links, lists, alignment, section styles, undo and redo, moving sections, five templates, photo left, right or off, and one or two pages. A live linter blocks "Mark ready" on factual problems. Exports: real Word from the edited document (`docx` library, photo included), print-to-PDF of the edited page, and the cloud-rendered PDF and Word.
- **Apply:** review checklist, status buttons, feedback chips, and the Apply Bridge.

Drafts save on the device. Marking a job submitted freezes the cloud model of the CV and cover letter that went with it.

## Apply Bridge (Mac only)

`bridge/bridge.mjs`, started from the Mac dashboard.

1. Opens the real employer URL in a dedicated Playwright profile (`~/madeline-jobs/playwright-profile`, gitignored).
2. Opens the form with an "Apply" link or button only when no form is on the page yet, and only if the element passes `safeToClick`.
3. Fills first name, last name, full name, email, phone, city and LinkedIn when the field is empty.
4. Uploads the CV PDF. Uploads the cover letter only when the employer allows AI-assisted material.
5. Leaves every sensitive field alone: gender, race, ethnicity, veteran, disability, criminal record, salary, sponsorship, relocation, travel, notice period, start date, health, age.
6. Lists required fields that are still empty.
7. Adds a banner, "APPLICATION PREPARED — NOT SUBMITTED", and leaves the window open.

## Never submit

- `safeToClick` refuses any element whose text, label, value or title mentions submit, send, finish, complete, confirm or the Greek equivalents, any `type=submit`, and anything inside a form that already holds file, email or text-area fields.
- A capture-phase listener cancels form submit events while the bridge is filling.
- CAPTCHA, MFA, bot checks and account creation are handed to the person in the window.

A test against Canonical's live form on 6 October 2026 found the first version clicked a "Submit application" button on the empty form before filling it. The page rejected it because required fields were empty and a CAPTCHA was present. The guards above were added the same day, and the rerun clicked nothing.

## Employer AI policy

Detected from phrases such as "your own words", "AI-generated", "plagiarism", "ChatGPT". When prohibited, the studio shows a banner, the bridge does not paste or upload the cover letter, and the Apply tab lists true facts she can draw on while writing the answers herself.
