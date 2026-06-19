import streamlit as st
import google.generativeai as genai
import io
import json
import re


# ----------------------------------------------------------------------------
# File reading helpers
# ----------------------------------------------------------------------------
def extract_text_from_pdf(file_bytes):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text


def extract_text_from_docx(file_bytes):
    from docx import Document
    doc = Document(io.BytesIO(file_bytes))
    return "\n".join(p.text for p in doc.paragraphs)


def extract_text_from_upload(uploaded_file):
    """Returns plain text content from an uploaded PDF, DOCX, or TXT file."""
    if uploaded_file is None:
        return ""
    name = uploaded_file.name.lower()
    file_bytes = uploaded_file.read()
    try:
        if name.endswith(".pdf"):
            return extract_text_from_pdf(file_bytes)
        elif name.endswith(".docx"):
            return extract_text_from_docx(file_bytes)
        elif name.endswith(".txt"):
            return file_bytes.decode("utf-8", errors="ignore")
        else:
            return ""
    except Exception as e:
        st.warning(f"Dili nabasa ang file ({uploaded_file.name}): {e}")
        return ""


def parse_json_from_model_text(text):
    """Strips markdown code fences and parses the first JSON object found."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned.strip())
    cleaned = re.sub(r"```$", "", cleaned.strip())
    cleaned = cleaned.strip()
    # Fallback: grab the substring between the first { and last }
    if not cleaned.startswith("{"):
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)
    return json.loads(cleaned)


def extract_details_with_ai(model, source_text):
    """Asks Gemini to pull structured DLL fields out of raw exemplar/source text."""
    extraction_prompt = f"""
Extract the following details from this lesson plan / curriculum document text.
Return ONLY a valid JSON object (no markdown fences, no commentary) with exactly these keys:

{{
  "learning_area": "string, e.g. 'English 9'",
  "teacher_name": "string, the teacher's name if found, else empty string",
  "teacher_role": "string, e.g. 'Teacher III', else empty string",
  "checker_name": "string, the name of whoever checked/reviewed it, else empty string",
  "checker_role": "string, e.g. 'Master Teacher II', else empty string",
  "grade_section": "string, e.g. 'Grade 9' or 'Grade 7 - Archimedes'",
  "competencies": ["array of strings, each one a distinct learning competency, including its code if present, e.g. 'EN8LIT-I-1 Analyze literary texts...'"],
  "objectives": "string, newline-separated list of learning objectives if found, else empty string"
}}

If a field cannot be found, use an empty string (or empty array for competencies). Do not invent information that isn't present in the text.

DOCUMENT TEXT:
{source_text[:12000]}
"""
    response = model.generate_content(extraction_prompt)
    return parse_json_from_model_text(response.text)


def reset_competencies(values):
    """Resets the dynamic competency list in session_state."""
    st.session_state.competencies = values if values else [""]


# ----------------------------------------------------------------------------
# Page setup
# ----------------------------------------------------------------------------
st.set_page_config(page_title="AI Daily Lesson Log (DLL) Planner", layout="wide")

st.markdown(
    """
    <div style="background-color:#1A56DB;padding:18px 24px;border-radius:8px;margin-bottom:20px;">
        <h2 style="color:white;margin:0;">📘 AI Daily Lesson Log (DLL) Planner</h2>
        <p style="color:#D6E4FF;margin:0;">DepEd MATATAG-aligned • AI-generated lesson plans</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------------
# Sidebar: API Key
# ----------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Setup")
    default_key = ""
    if hasattr(st, "secrets"):
        try:
            default_key = st.secrets.get("GEMINI_API_KEY", "")
        except Exception:
            default_key = ""
    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        help="Kuhaa sa https://aistudio.google.com/apikey",
        value=default_key,
    )
    st.caption("Ang imong API key dili na-save bisan asa. Gamiton ra sa kasamtangang session.")
    st.divider()
    st.caption("Developed with reference to the AI DLL Planner Gem.")

if api_key:
    genai.configure(api_key=api_key)

MODEL_NAME = "gemini-3.5-flash"  # current GA fast model as of mid-2026

# ----------------------------------------------------------------------------
# Session state defaults
# ----------------------------------------------------------------------------
defaults = {
    "competencies": [""],
    "learning_area": "",
    "teacher_name": "",
    "teacher_role": "",
    "checker_name": "",
    "checker_role": "",
    "grade_section": "",
    "objectives": "",
    "extraction_status": None,  # None | "success" | "error"
    "extraction_message": "",
    "last_processed_file": None,
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ----------------------------------------------------------------------------
# Main layout: two columns
# ----------------------------------------------------------------------------
col1, col2 = st.columns([1, 1.3])

with col1:
    st.subheader("📝 Lesson Details")

    language = st.radio("Language / Wika *", ["English", "Filipino"], horizontal=True)

    input_mode = st.radio(
        "Input Mode *",
        ["A. Manual Input", "B. Upload Exemplar", "C. Upload Other Sources"],
        horizontal=True,
    )

    other_sources_text = ""

    # ------------------------------------------------------------------
    # B. Upload Exemplar — auto-extracts structured fields via Gemini
    # ------------------------------------------------------------------
    if input_mode == "B. Upload Exemplar":
        with st.container(border=True):
            st.markdown("**📄 Upload Lesson Exemplar**")
            st.caption(
                "Upload a PDF, DOCX, or TXT. The AI will automatically extract details "
                "and use it as the main reference guide."
            )
            exemplar_file = st.file_uploader(
                "Choose File",
                type=["pdf", "docx", "txt"],
                key="exemplar",
                label_visibility="collapsed",
            )

            if exemplar_file is not None:
                # Only re-run extraction if this is a new file (avoid re-running on every rerender)
                file_signature = f"{exemplar_file.name}-{exemplar_file.size}"
                if st.session_state.last_processed_file != file_signature:
                    if not api_key:
                        st.session_state.extraction_status = "error"
                        st.session_state.extraction_message = (
                            "Palihog ilagay una ang Gemini API Key sa sidebar para mahimo ang extraction."
                        )
                    else:
                        with st.spinner("Gi-analyze ang imong file..."):
                            try:
                                raw_text = extract_text_from_upload(exemplar_file)
                                if not raw_text.strip():
                                    st.session_state.extraction_status = "error"
                                    st.session_state.extraction_message = (
                                        "Walay nabasa nga text sa file (basin scanned image nga PDF)."
                                    )
                                else:
                                    extractor_model = genai.GenerativeModel(MODEL_NAME)
                                    data = extract_details_with_ai(extractor_model, raw_text)

                                    st.session_state.learning_area = data.get("learning_area", "") or st.session_state.learning_area
                                    st.session_state.teacher_name = data.get("teacher_name", "") or st.session_state.teacher_name
                                    st.session_state.teacher_role = data.get("teacher_role", "") or st.session_state.teacher_role
                                    st.session_state.checker_name = data.get("checker_name", "") or st.session_state.checker_name
                                    st.session_state.checker_role = data.get("checker_role", "") or st.session_state.checker_role
                                    st.session_state.grade_section = data.get("grade_section", "") or st.session_state.grade_section
                                    st.session_state.objectives = data.get("objectives", "") or st.session_state.objectives

                                    extracted_competencies = [c for c in data.get("competencies", []) if c.strip()]
                                    if extracted_competencies:
                                        reset_competencies(extracted_competencies)

                                    st.session_state.extraction_status = "success"
                                    st.session_state.extraction_message = "Data extracted successfully! Ready to generate."
                            except json.JSONDecodeError:
                                st.session_state.extraction_status = "error"
                                st.session_state.extraction_message = (
                                    "Dili masabtan sa AI ang format sa file. Sulayi og lain nga file o i-type lang manually."
                                )
                            except Exception as e:
                                st.session_state.extraction_status = "error"
                                st.session_state.extraction_message = f"Naay sayop: {e}"

                    st.session_state.last_processed_file = file_signature

                if st.session_state.extraction_status == "success":
                    st.success(f"✅ {st.session_state.extraction_message}")
                elif st.session_state.extraction_status == "error":
                    st.error(f"⚠️ {st.session_state.extraction_message}")

    # ------------------------------------------------------------------
    # C. Upload Other Sources — used as raw reference context, not auto-filled
    # ------------------------------------------------------------------
    elif input_mode == "C. Upload Other Sources":
        other_files = st.file_uploader(
            "I-upload ang reference materials (curriculum guide, textbook excerpt, atbp.)",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=True,
            key="other_sources",
        )
        if other_files:
            texts = []
            for f in other_files:
                t = extract_text_from_upload(f)
                if t:
                    texts.append(f"--- {f.name} ---\n{t}")
            other_sources_text = "\n\n".join(texts)
            if other_sources_text:
                st.success(f"Na-load ang {len(other_files)} file(s).")

    # ------------------------------------------------------------------
    # Shared fields (auto-filled if extraction ran, editable regardless)
    # ------------------------------------------------------------------
    learning_area = st.text_input(
        "Learning Area/s *", placeholder="e.g. Science 7", key="learning_area"
    )

    c1, c2 = st.columns(2)
    with c1:
        teacher_name = st.text_input(
            "Designed by Teacher/s *", placeholder="e.g. Juan Dela Cruz", key="teacher_name"
        )
    with c2:
        teacher_role = st.text_input(
            "Teacher Role", placeholder="e.g. Teacher III", key="teacher_role"
        )

    c3, c4 = st.columns(2)
    with c3:
        checker_name = st.text_input(
            "Checked by *", placeholder="e.g. Maria Santos", key="checker_name"
        )
    with c4:
        checker_role = st.text_input(
            "Checker Role", placeholder="e.g. Master Teacher II", key="checker_role"
        )

    grade_section = st.text_input(
        "Grade Level and Section *", placeholder="e.g. Grade 7 - Archimedes", key="grade_section"
    )

    num_days = st.selectbox(
        "No. of DLLs to Generate *",
        options=[1, 2, 3, 4, 5],
        index=3,
        format_func=lambda x: f"{x} Day{'s' if x > 1 else ''} ({x} Separate DLL{'s' if x > 1 else ''})",
    )
    st.caption("ℹ️ Maghimo ang AI og separate table alang sa kada adlaw.")

    # ------------------------------------------------------------------
    # Dynamic Learning Competency list
    # ------------------------------------------------------------------
    st.markdown("**Learning Competency/ies** *")
    for i in range(len(st.session_state.competencies)):
        row_col1, row_col2 = st.columns([10, 1])
        with row_col1:
            st.session_state.competencies[i] = st.text_area(
                f"competency_{i}",
                value=st.session_state.competencies[i],
                placeholder="e.g. Identify parts of the microscope and their functions. (S7LT-IIa-1)",
                height=70,
                label_visibility="collapsed",
                key=f"competency_box_{i}",
            )
        with row_col2:
            if len(st.session_state.competencies) > 1:
                if st.button("🗑️", key=f"delete_competency_{i}"):
                    st.session_state.competencies.pop(i)
                    st.rerun()

    if st.button("➕ Add another competency"):
        st.session_state.competencies.append("")
        st.rerun()

    objectives = st.text_area(
        "Learning Objectives (Optional)",
        placeholder="1. Identify the major parts of a compound light microscope.\n2. Classify the parts according to their function.",
        height=100,
        key="objectives",
    )

    generate_btn = st.button("✏️ Generate Lesson Plan", type="primary", use_container_width=True)

with col2:
    st.subheader("📄 Generated Lesson Plan(s)")

    output_area = st.container()

    if generate_btn:
        competencies_clean = [c.strip() for c in st.session_state.competencies if c.strip()]

        # --- Validation ---
        missing = []
        if not api_key:
            missing.append("Gemini API Key (sa sidebar)")
        if not learning_area:
            missing.append("Learning Area/s")
        if not teacher_name:
            missing.append("Designed by Teacher/s")
        if not checker_name:
            missing.append("Checked by")
        if not grade_section:
            missing.append("Grade Level and Section")
        if not competencies_clean:
            missing.append("Learning Competency/ies")

        if missing:
            output_area.error(
                "⚠️ Palihog kompletoha ning mga kinahanglanon nga field:\n\n"
                + "\n".join(f"- {m}" for m in missing)
            )
        else:
            with output_area:
                with st.spinner("Binubuo ang imong lesson plan..."):
                    try:
                        model = genai.GenerativeModel(MODEL_NAME)

                        competency_block = "\n".join(f"- {c}" for c in competencies_clean)

                        extra_context = ""
                        if input_mode == "C. Upload Other Sources" and other_sources_text:
                            extra_context = (
                                "Gamita kini nga reference materials isip BASEHANAN sa sulod sa leksyon "
                                "(curriculum guide, textbook excerpt, ubp.):\n"
                                + other_sources_text[:6000]
                            )

                        prompt = f"""
You are an expert Filipino public school teacher creating DepEd MATATAG-aligned Daily Lesson Logs (DLL).

Generate a {num_days}-day Daily Lesson Log (DLL) with the following details:

- Language to write the lesson plan in: {language}
- Learning Area/s: {learning_area}
- Designed by Teacher/s: {teacher_name} ({teacher_role or "Teacher"})
- Checked by: {checker_name} ({checker_role or "Master Teacher"})
- Grade Level and Section: {grade_section}
- Learning Competency/ies:
{competency_block}
- Learning Objectives: {objectives if objectives else "Derive appropriate objectives from the competencies above."}

{extra_context}

INSTRUCTIONS:
1. Create {num_days} SEPARATE tables, one per day (Day 1 to Day {num_days}).
2. Distribute and sequence the listed competencies logically across the {num_days} days (don't necessarily cram all of them into Day 1).
3. Each table must use the standard DepEd DLL rows in this exact order:
   - Balik-aral (Review)
   - Pagganyak (Motivation)
   - Paglalahad/Talakayan (Presentation/Discussion)
   - Paglalapat (Application)
   - Paglalahat (Generalization)
   - Pagtataya (Assessment/Evaluation)
4. Each cell should contain specific, classroom-ready content (actual activities, sample questions, or instructions) — not generic placeholders.
5. Make sure content builds progressively across days when relevant (e.g. Day 1 review feeds into Day 2).
6. Format the entire output in clean Markdown, with a level-2 heading for each day (## Day 1, ## Day 2, etc.) followed by a Markdown table with two columns: "Yugto ng Aralin" and the content for that day.
7. At the top, include a header block with: Learning Area, Teacher, Checked by, Grade & Section, and Learning Competency/ies (list all of them).
8. Do not include any commentary outside the lesson plan itself.
"""
                        response = model.generate_content(prompt)
                        st.markdown(response.text)

                        st.download_button(
                            "⬇️ Download as Markdown",
                            data=response.text,
                            file_name=f"DLL_{learning_area.replace(' ', '_')}.md",
                            mime="text/markdown",
                        )

                    except Exception as e:
                        st.error(f"Naay sayop nga nahitabo: {e}")
    else:
        output_area.info(
            "🤖 Ilagay ang detalye sa wala para makabuo og lesson plan.\n\n"
            "Maghimo ang AI og separate, complete nga DLL kada adlaw, base sa DepEd guidelines."
        )

st.divider()
st.caption("⚠️ AI-generated content — palihog susiha ug i-adjust base sa imong klase ug konteksto sa eskwelahan.")
