# DocuMind Kenya: Product Direction and Improvement Plan

This document records the product direction so future work can build toward a coherent, useful system. It is a working plan, not a claim that every capability below already exists.

## Product purpose

DocuMind helps people turn trusted documents into clear, source-grounded work they can use. In Kenya, the first focus is education and training: help teachers prepare lessons and practice from approved materials, help learners understand and practise, and help institutions follow through on learning needs.

The longer-term opportunity is a shared knowledge-to-action platform for schools, TVET colleges, and later businesses. The product should earn that expansion through evidence of value in one initial workflow.

## The first user and recurring problem

Start with teachers and trainers who repeatedly turn curriculum documents, notes, and manuals into explanations, activities, quizzes, and revision materials. Give them a fast path from source material to a draft they can review, adapt, print, and use.

The first workflow is:

1. Upload or select an authorized, relevant document.
2. Choose a ready-made teaching task or ask a question in ordinary language.
3. Get a clear draft grounded in the document, with source references.
4. Review and adapt the output before sharing it with learners.
5. Keep the conversation under the source file and revisit or print the useful answer.
6. Later, use formative learner results to plan targeted practice and follow-up.

DocuMind supports teachers; it does not replace their judgment. Generated material must remain reviewable, editable, and traceable to its source. If the source does not specify a grade, objective, or requirement, the system should say so rather than invent one.

## Why this is relevant in Kenya

Kenya's education strategy includes digital curriculum materials, teacher training, and digital learning priorities. Young people also report concerns about work, training, and the match between education and job requirements. These are reasons to investigate practical education and skills workflows; they are not proof that an AI product alone can resolve those structural challenges.

Useful evidence for future product discovery:

- [Ministry of Education, National Education Sector Strategic Plan 2023–2027](https://www.education.go.ke/index.php/sites/default/files/2024-07/NATIONAL%20EDUCATION%20STRATEGIC%20PLAN%202023-2027-compressed_removed_0.pdf)
- [Afrobarometer, Kenyan youth and their top priorities](https://www.afrobarometer.org/publication/ad988-most-kenyan-youth-see-government-as-failing-on-their-top-priorities/)
- [Ministry of ICT, Digital Skills](https://ict.go.ke/digital-skills)
- [KNBS, 2026 Economic Survey](https://www.knbs.or.ke/reports/2026-economic-survey/)

These sources should inform discovery, not substitute for interviews with teachers, learners, headteachers, trainers, employers, and buyers.

## Product principles

- **Easy first use:** show a new user useful examples and provide one-click tasks; do not require prompt-writing expertise.
- **Grounded answers:** cite source documents and pages where available. Make uncertainty visible.
- **Teacher control:** users review and approve generated teaching materials.
- **Useful in real classrooms:** make outputs concise, printable, adaptable, and usable with few special materials.
- **Learning over answer copying:** support hints, practice, explanations, and teach-back.
- **Privacy by design:** minimize learner data, use clear access boundaries, and design carefully for children and schools.
- **Evidence before claims:** measure time saved, quality, adoption, and learning indicators before making impact claims.
- **Authorized content:** institutions should use materials they have permission to upload and process.

## Initial feature: teacher-ready teaching pack

The first guided task should generate a practical draft from the selected file:

- Topic and learning objectives; mark unspecified details as “Teacher to fill in.”
- A short lesson sequence.
- A plain-language explanation and examples grounded in the source.
- An activity that can work with few or no special materials.
- Practice at support, standard, and challenge levels.
- A short formative quiz with an answer key.
- Likely misconceptions and suggested follow-up.
- Source references beside claims and answers.

The teacher should be able to print or save the answer as a PDF using the browser. Conversation history remains attached to the document so the teacher can reopen the work later.

## Expansion paths after the first workflow is validated

### Learners

- Explain concepts in simpler language and offer examples.
- Give hints before complete answers.
- Create short, source-based practice and answer explanations.
- Support English and Kiswahili where the source and user request allow.
- Keep learning support separate from high-stakes automated grading or placement.

### Headteachers and institution leaders

- Turn circulars, policies, calendars, and approved plans into cited requirements, deadlines, and staff action lists.
- Track completion and prepare communication or reporting drafts.
- Provide aggregate progress views without exposing private learner chats by default.

### TVET colleges and workforce preparation

- Convert authorized manuals and unit materials into step-by-step practice, safety checklists, and competency evidence logs.
- Help learners assemble portfolios from real, reviewed work.
- Validate skill mappings with trainers and employers; never imply that AI output is a certificate.

### Businesses (later)

- Use approved company documents to create source-grounded SOP checklists, tender response matrices, and customer support drafts.
- Add organization roles, approvals, audit history, and stronger data controls before targeting sensitive enterprise workflows.

## Validation plan

Before broad expansion, interview teachers, school leaders, TVET trainers, learners, and prospective buyers. Ask them to demonstrate the actual task, not just react to a product pitch. Select one subject or training unit and run a small pilot with an agreed baseline.

Measure:

- Preparation time before and after using the workflow.
- How often packs are used, edited, or rejected.
- Accuracy of source references and factual review findings.
- Teacher and learner repeat use.
- Completion of practice and follow-up activities.
- Comparable short formative checks before and after instruction.
- Willingness to pay, renewal intent, and support burden for the institution.

A small pilot can reveal usability and quality issues. It cannot by itself establish that the product caused a learning gain; impact claims need a stronger evaluation design.

## Roadmap

### Now: make the existing document assistant useful for teachers

- Add an obvious one-click teaching-pack prompt and learner-practice examples.
- Keep chats nested under their source files and make them easy to revisit.
- Let users print a useful answer with its cited sources.
- Keep upload, chat, and history interactions straightforward on mobile.

### Next: school and college workflow foundations

- Add organization workspaces, member roles, and source-level permissions.
- Add education metadata such as level, subject, topic, term, and competency.
- Support editable, versioned teaching packs and approved shared resources.
- Add OCR for scanned documents and improve low-data and print workflows.
- Add privacy-aware, aggregate formative assessment insights.

### Later: validated institution and workforce workflows

- Add TVET competency practice and reviewed portfolio evidence.
- Add employer-informed skill maps and institution reporting.
- Explore business document workflows after validating demand and security requirements.

## Important current limitations

The current product is a private document upload, search, chat, and history tool. It does not yet provide organization accounts, curriculum alignment metadata, learner assessment analytics, offline operation, or OCR for scanned PDFs. Answers and generated teaching material need human review even when citations are shown.

Do not store identifiable child assessment data in pilots without appropriate institutional approval, consent, safeguards, and legal review. Confirm education content rights before uploading or distributing materials. Avoid using DocuMind for high-stakes grading, admissions, placement, or employment decisions.

## Product description to test

> DocuMind helps Kenyan schools and colleges turn approved learning materials into cited lesson plans, practice, quizzes, and targeted revision—while keeping teachers in control.

Test this wording with users. Replace it if interviews show a more urgent, measurable workflow.
