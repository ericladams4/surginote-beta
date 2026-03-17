GENERAL_SURGERY_MODULES = [
    {
        "key": "appendicitis_consult",
        "label": "Appendicitis Consult",
        "rank": 1,
        "note_type": "consult_note",
        "description": "Short, believable acute appendicitis consults with clean HPI, imaging incorporation, exam placement, and operative plan wording.",
    },
    {
        "key": "cholecystitis_consult",
        "label": "Cholecystitis Consult",
        "rank": 2,
        "note_type": "consult_note",
        "description": "Acute cholecystitis consults that teach concise biliary history, imaging summary, surgeon-like plan language, and appropriate assumptions.",
    },
    {
        "key": "small_bowel_obstruction_consult",
        "label": "Small Bowel Obstruction Consult",
        "rank": 3,
        "note_type": "consult_note",
        "description": "Nonoperative SBO consults with clear chronology, decompression status, exam wording, and escalation planning.",
    },
    {
        "key": "diverticulitis_consult",
        "label": "Diverticulitis Consult",
        "rank": 4,
        "note_type": "consult_note",
        "description": "Diverticulitis consults that stay surgically focused without turning into long medicine-style discussions.",
    },
    {
        "key": "hernia_consult",
        "label": "Hernia Consult",
        "rank": 5,
        "note_type": "consult_note",
        "description": "Urgent hernia consults with focused exam, imaging, and action-oriented planning.",
    },
    {
        "key": "appendectomy_op_note",
        "label": "Appendectomy Op Note",
        "rank": 6,
        "note_type": "op_note",
        "description": "Straightforward laparoscopic appendectomy operative notes with believable findings and efficient procedural sequencing.",
    },
    {
        "key": "cholecystectomy_op_note",
        "label": "Cholecystectomy Op Note",
        "rank": 7,
        "note_type": "op_note",
        "description": "Laparoscopic or robotic cholecystectomy operative notes with concise findings and surgeon-like flow.",
    },
    {
        "key": "postop_followup_clinic",
        "label": "Post-op Follow-up",
        "rank": 8,
        "note_type": "clinic_note",
        "description": "Routine postoperative clinic documentation with interval recovery, wound review, pathology, and follow-up instructions.",
    },
    {
        "key": "elective_hernia_clinic",
        "label": "Elective Hernia Clinic",
        "rank": 9,
        "note_type": "clinic_note",
        "description": "Elective hernia clinic notes with focused symptom summary, operative counseling, and disposition language.",
    },
    {
        "key": "elective_biliary_clinic",
        "label": "Elective Biliary Clinic",
        "rank": 10,
        "note_type": "clinic_note",
        "description": "Outpatient biliary clinic notes with concise symptom history, imaging review, and operative counseling.",
    },
]

GENERAL_SURGERY_MODULE_MAP = {module["key"]: module for module in GENERAL_SURGERY_MODULES}

SCENARIO_BLUEPRINTS = [
    {
        "specialty": "General Surgery",
        "module_key": "appendicitis_consult",
        "note_type": "consult_note",
        "title": "Acute appendicitis admit from ED",
        "diagnosis": "Acute appendicitis",
        "procedure_focus": "Laparoscopic appendectomy",
        "complexity_level": 1,
        "scenario_brief": (
            "Presentation:\n"
            "34-year-old man with no known prior medical or surgical history presents to the emergency department with 18 hours of abdominal pain that began near the umbilicus and has migrated to the lower abdomen. He reports nausea and anorexia and says the pain has progressively worsened overnight. He denies hematemesis, melena, prior similar episodes, or other abdominal operations.\n\n"
            "Workup:\n"
            "Computed tomography of the abdomen and pelvis demonstrates uncomplicated acute appendicitis without perforation, abscess, or free air. White blood cell count is 14 with otherwise unremarkable chemistry. On exam he is hemodynamically stable, uncomfortable but not toxic, with focal lower abdominal tenderness and no diffuse peritonitis.\n\n"
            "Current status / surgical question:\n"
            "Medicine admitted him overnight, started intravenous fluids, kept him nothing by mouth, and gave ceftriaxone plus metronidazole. Surgery is being asked to evaluate for appendectomy during this admission and document the immediate operative plan."
        ),
        "learning_objectives": "Teach efficient appendicitis consult structure, concise HPI, proper assumption handling for RLQ tenderness, and a practical overnight operative plan.",
    },
    {
        "specialty": "General Surgery",
        "module_key": "cholecystitis_consult",
        "note_type": "consult_note",
        "title": "Acute cholecystitis for robotic chole",
        "diagnosis": "Acute cholecystitis",
        "procedure_focus": "Robotic cholecystectomy",
        "complexity_level": 1,
        "scenario_brief": (
            "Presentation:\n"
            "62-year-old woman with hypertension and obesity presents with 24 hours of right upper abdominal pain that began after a fatty meal and has been associated with nausea and poor oral intake. She denies jaundice, chest pain, or shortness of breath. She has not had prior abdominal surgery.\n\n"
            "Workup:\n"
            "Ultrasound shows gallstones, gallbladder wall thickening, and trace pericholecystic fluid. Computed tomography of the abdomen and pelvis also supports acute cholecystitis without perforation or abscess. White blood cell count is 15 and total bilirubin is normal. She is afebrile, hemodynamically stable, and has focal right upper abdominal tenderness without diffuse peritonitis.\n\n"
            "Current status / surgical question:\n"
            "Medicine admitted her, started intravenous fluids and antibiotics, and is asking surgery to evaluate for cholecystectomy during this admission. The intended operative approach, if feasible, is robotic."
        ),
        "learning_objectives": "Teach biliary consult tone, correct RUQ assumption logic, concise imaging/lab incorporation, and a surgeon-like operative recommendation.",
    },
    {
        "specialty": "General Surgery",
        "module_key": "small_bowel_obstruction_consult",
        "note_type": "consult_note",
        "title": "Small bowel obstruction with transition point",
        "diagnosis": "Small bowel obstruction",
        "procedure_focus": "Nonoperative management",
        "complexity_level": 1,
        "scenario_brief": (
            "Presentation:\n"
            "67-year-old man with a history of prior open sigmoid colectomy for diverticulitis presents with one day of progressive abdominal pain, bloating, nausea, and several episodes of non-bloody vomiting. He has not passed flatus since yesterday morning. He reports no recent bowel movement and says this feels similar to a prior obstruction admission.\n\n"
            "Workup:\n"
            "Computed tomography of the abdomen and pelvis demonstrates dilated small bowel with a transition point in the mid abdomen, without pneumatosis, portal venous gas, or free intraperitoneal air. Lactate is normal and white blood cell count is mildly elevated. Exam shows abdominal distension and mild diffuse tenderness without rebound or guarding.\n\n"
            "Current status / surgical question:\n"
            "A nasogastric tube has already been placed with immediate bilious output, he has been kept nothing by mouth, and intravenous fluids are running. Surgery is being consulted for nonoperative management recommendations and for guidance on what findings would prompt escalation to urgent operation."
        ),
        "learning_objectives": "Teach SBO consult phrasing, appropriate nonoperative planning, and keeping HPI contiguous without duplicative narrative.",
    },
    {
        "specialty": "General Surgery",
        "module_key": "diverticulitis_consult",
        "note_type": "consult_note",
        "title": "Perforated diverticulitis with abscess",
        "diagnosis": "Complicated diverticulitis",
        "procedure_focus": "Drain vs operative planning",
        "complexity_level": 2,
        "scenario_brief": (
            "Presentation:\n"
            "58-year-old man with known diverticulosis presents with three days of worsening left lower abdominal pain, subjective fevers, and poor appetite. He says this episode feels worse than his prior uncomplicated diverticulitis flares. He denies generalized abdominal rigidity or syncope.\n\n"
            "Workup:\n"
            "Computed tomography of the abdomen and pelvis demonstrates sigmoid diverticulitis with a 4.5 centimeter pericolic abscess and surrounding inflammatory change, but no diffuse free air or generalized contamination. White blood cell count is 17 and lactate is normal. He is hemodynamically stable and tender in the left lower abdomen with focal guarding but no diffuse peritonitis.\n\n"
            "Current status / surgical question:\n"
            "He is receiving intravenous antibiotics and fluids on the medicine service. Surgery is being asked to weigh in on admission management, whether interventional radiology drainage versus operative intervention is more appropriate, and what interval follow-up planning should look like if he improves."
        ),
        "learning_objectives": "Teach escalation from straightforward consults into more nuanced operative versus IR drain decision-making.",
    },
    {
        "specialty": "General Surgery",
        "module_key": "hernia_consult",
        "note_type": "consult_note",
        "title": "Incarcerated umbilical hernia consult",
        "diagnosis": "Incarcerated umbilical hernia",
        "procedure_focus": "Urgent hernia evaluation",
        "complexity_level": 1,
        "scenario_brief": (
            "Presentation:\n"
            "52-year-old man presents with one day of increasing pain at a known umbilical hernia along with nausea and inability to reduce the bulge at home. He denies diffuse abdominal pain and has not had prior hernia repair.\n\n"
            "Workup:\n"
            "Computed tomography of the abdomen and pelvis shows fat and a short segment of small bowel within the umbilical hernia without free air or obvious perforation. Lactate is normal and white blood cell count is mildly elevated. Exam shows a tender nonreducible umbilical hernia without diffuse peritonitis.\n\n"
            "Current status / surgical question:\n"
            "He has received intravenous fluids and pain medication in the emergency department. Surgery is being asked to evaluate whether urgent operation is needed and to document the immediate management plan."
        ),
        "learning_objectives": "Teach focused urgent hernia consult structure and concise action-oriented planning.",
    },
    {
        "specialty": "General Surgery",
        "module_key": "appendectomy_op_note",
        "note_type": "op_note",
        "title": "Routine laparoscopic appendectomy",
        "diagnosis": "Acute appendicitis",
        "procedure_focus": "Laparoscopic appendectomy",
        "complexity_level": 1,
        "scenario_brief": (
            "Indication:\n"
            "Healthy adult taken urgently to the operating room after emergency department workup confirmed acute uncomplicated appendicitis. Preoperative imaging showed no perforation or abscess, and the patient received antibiotics before incision.\n\n"
            "Intraoperative findings:\n"
            "The appendix is inflamed and thickened but not perforated or gangrenous, and there is no abscess or generalized contamination. The cecal base appears healthy.\n\n"
            "Procedure / disposition:\n"
            "A standard laparoscopic appendectomy is performed. The mesoappendix is divided with an energy device, the appendiceal base is stapled, and the specimen is removed in an endoscopic bag. Hemostasis is excellent with no enteric spillage. Estimated blood loss is minimal, no drain is left, and the patient is extubated and transferred to the recovery unit in stable condition."
        ),
        "learning_objectives": "Teach clean, believable operative sequencing and concise procedure prose.",
    },
    {
        "specialty": "General Surgery",
        "module_key": "cholecystectomy_op_note",
        "note_type": "op_note",
        "title": "Robotic cholecystectomy for acute cholecystitis",
        "diagnosis": "Acute cholecystitis",
        "procedure_focus": "Robotic cholecystectomy",
        "complexity_level": 1,
        "scenario_brief": (
            "Indication:\n"
            "Patient is taken to the operating room during the index admission for acute cholecystitis after preoperative imaging and laboratory evaluation supported biliary source infection without evidence of perforation.\n\n"
            "Intraoperative findings:\n"
            "At the start of the case the gallbladder is distended, edematous, and inflamed, but there is no obvious perforation. Adhesions are limited and the anatomy allows a clean critical view of safety.\n\n"
            "Procedure / disposition:\n"
            "A robotic cholecystectomy is performed. The cystic duct and cystic artery are clipped and divided after the critical view is confirmed, and the gallbladder is dissected from the liver bed and removed intact in a specimen bag. Hemostasis is confirmed and there is no bile leak. Estimated blood loss is minimal, no drain is left, and the patient is transferred to the recovery unit in stable condition."
        ),
        "learning_objectives": "Teach robotic biliary operative documentation and surgeon-like procedural detail density.",
    },
    {
        "specialty": "General Surgery",
        "module_key": "postop_followup_clinic",
        "note_type": "clinic_note",
        "title": "Post-op chole follow-up",
        "diagnosis": "Status post cholecystectomy",
        "procedure_focus": "Postoperative clinic note",
        "complexity_level": 1,
        "scenario_brief": (
            "Presentation:\n"
            "Two-week postoperative clinic follow-up after uncomplicated robotic cholecystectomy for acute cholecystitis. The patient reports steadily improving abdominal soreness, is off narcotic medication, and is tolerating a regular diet without nausea or diarrhea. She denies fever, jaundice, or wound drainage.\n\n"
            "Workup:\n"
            "Clinic exam shows healing port sites without erythema, drainage, or dehiscence. Final pathology demonstrates chronic cholecystitis with cholelithiasis and no malignancy.\n\n"
            "Current status / surgical question:\n"
            "The note should document interval recovery, wound status, pathology review, and discharge-from-clinic style follow-up instructions."
        ),
        "learning_objectives": "Teach concise post-op clinic tone and practical follow-up planning.",
    },
    {
        "specialty": "General Surgery",
        "module_key": "elective_hernia_clinic",
        "note_type": "clinic_note",
        "title": "Elective inguinal hernia clinic evaluation",
        "diagnosis": "Symptomatic inguinal hernia",
        "procedure_focus": "Elective hernia repair planning",
        "complexity_level": 1,
        "scenario_brief": (
            "Presentation:\n"
            "55-year-old man is seen in clinic for a right groin bulge that has been present for several months and is more noticeable after standing or lifting at work. He reports intermittent discomfort but no obstructive symptoms, skin changes, or episodes of incarceration. He has no prior abdominal surgery and is otherwise healthy.\n\n"
            "Workup:\n"
            "Physical exam demonstrates a reducible right inguinal hernia without overlying skin change or tenderness. No imaging has been required because the exam is straightforward.\n\n"
            "Current status / surgical question:\n"
            "The note should document symptom burden, exam findings, and the counseling/plan for elective hernia repair versus watchful waiting in a concise surgeon-like clinic style."
        ),
        "learning_objectives": "Teach clean elective hernia clinic documentation and concise operative counseling language.",
    },
    {
        "specialty": "General Surgery",
        "module_key": "elective_biliary_clinic",
        "note_type": "clinic_note",
        "title": "Elective biliary colic clinic visit",
        "diagnosis": "Symptomatic cholelithiasis",
        "procedure_focus": "Elective cholecystectomy planning",
        "complexity_level": 1,
        "scenario_brief": (
            "Presentation:\n"
            "41-year-old woman is referred to clinic after several episodes of postprandial right upper abdominal pain associated with nausea, usually after fatty meals. Symptoms resolve between attacks and she has never been jaundiced or hospitalized for this problem. She has no prior abdominal surgery.\n\n"
            "Workup:\n"
            "Ultrasound shows gallstones without gallbladder wall thickening or biliary ductal dilation. Liver tests are normal. Exam in clinic is benign.\n\n"
            "Current status / surgical question:\n"
            "The note should capture a focused biliary symptom history, imaging review, and straightforward counseling/plan for elective cholecystectomy."
        ),
        "learning_objectives": "Teach concise elective biliary clinic note structure and surgeon-like operative counseling.",
    },
    {
        "specialty": "Colorectal Surgery",
        "note_type": "consult_note",
        "title": "Recurrent diverticulitis surgical consult",
        "diagnosis": "Recurrent diverticulitis",
        "procedure_focus": "Elective sigmoid colectomy planning",
        "complexity_level": 2,
        "scenario_brief": (
            "Presentation:\n"
            "49-year-old woman with several prior documented diverticulitis episodes is admitted with another computed tomography-confirmed sigmoid flare. She had severe left lower abdominal pain and low-grade fever on arrival but is now improving after 24 hours of intravenous antibiotics. She has never required emergent surgery.\n\n"
            "Workup:\n"
            "Imaging shows active sigmoid inflammation without abscess, obstruction, or free perforation. She remains hemodynamically stable and says recurrent episodes are increasingly affecting work and quality of life.\n\n"
            "Current status / surgical question:\n"
            "Colorectal surgery is being asked to comment on the current admission plan, when elective sigmoid colectomy would become appropriate, and how interval follow-up should be framed after this flare resolves."
        ),
        "learning_objectives": "Teach colorectal consult structure and operative planning language that differs from emergency general surgery.",
    },
    {
        "specialty": "Breast Surgery",
        "note_type": "clinic_note",
        "title": "New breast mass evaluation",
        "diagnosis": "Breast mass",
        "procedure_focus": "Breast clinic consultation",
        "complexity_level": 1,
        "scenario_brief": (
            "Presentation:\n"
            "46-year-old woman is referred to breast clinic after noticing a palpable left breast mass for several weeks. She denies nipple discharge, skin dimpling, fevers, or prior breast surgery. Family history is notable for a maternal aunt with breast cancer.\n\n"
            "Workup:\n"
            "Diagnostic mammogram and targeted ultrasound show a 1.8 centimeter irregular suspicious lesion in the left breast. Core biopsy has been ordered but pathology is not yet available. On exam there is a palpable mass without overlying skin changes or concerning axillary symptoms.\n\n"
            "Current status / surgical question:\n"
            "The note should capture a focused breast clinic history, pertinent imaging, exam context, and next-step planning without sounding like generic general surgery documentation."
        ),
        "learning_objectives": "Teach breast clinic note structure and specialty-specific tone rather than general surgery boilerplate.",
    },
    {
        "specialty": "Trauma / Acute Care Surgery",
        "module_key": "hernia_consult",
        "note_type": "consult_note",
        "title": "Acute care surgery consult for incarcerated ventral hernia",
        "diagnosis": "Incarcerated ventral hernia",
        "procedure_focus": "Urgent operative evaluation",
        "complexity_level": 2,
        "scenario_brief": (
            "Presentation:\n"
            "73-year-old woman with obesity and prior laparotomy presents with acute pain at the site of a known ventral hernia along with nausea and inability to reduce the bulge at home. Symptoms began earlier today and have progressed despite rest. She reports no diffuse abdominal rigidity or collapse.\n\n"
            "Workup:\n"
            "Computed tomography of the abdomen and pelvis demonstrates incarcerated small bowel within the ventral hernia sac with upstream dilation, but no frank pneumatosis, free air, or obvious bowel ischemia. White blood cell count is elevated and lactate is normal. She is uncomfortable but hemodynamically stable, and exam shows a tender nonreducible ventral hernia without diffuse peritonitis.\n\n"
            "Current status / surgical question:\n"
            "Acute care surgery is being consulted to determine whether urgent operative repair is needed tonight and to document the immediate management plan."
        ),
        "learning_objectives": "Teach urgent ACS consult tone, hernia-specific exam wording, and action-oriented planning.",
    },
]
