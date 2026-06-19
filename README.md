# AI Daily Lesson Log (DLL) Planner

Streamlit app nga maghimo og DepEd MATATAG-aligned Daily Lesson Logs gamit ang Gemini AI.

## Mga Features
- **3 Input Modes**: Manual Input, Upload Exemplar (sample DLL para sundon ang format), Upload Other Sources (curriculum guide/textbook para basehan ang sulod)
- Tanan standard DepEd fields: Teacher, Checker, Roles, Grade/Section, Learning Competency code, Objectives
- Mag-generate og 1-5 days nga separate DLL tables
- Download button para sa output (Markdown format)

## Paagi sa Pag-setup ug Deploy (Streamlit Community Cloud — libre)

### 1. Kuhaa ang Gemini API Key
1. Adto sa https://aistudio.google.com/apikey
2. Sign in sa Google account
3. Click "Create API Key" → kopyaha

### 2. I-upload ang code sa GitHub
1. Gumawa og bag-ong GitHub repository (e.g. `dll-planner`)
2. I-upload ang `app.py` ug `requirements.txt`
   - **HUWAT**: Dili gyud i-type ang API key direkta sa code. Gamiton ang Streamlit Secrets (tan-awa sa ubos).

### 3. I-deploy sa Streamlit Community Cloud
1. Adto sa https://share.streamlit.io
2. Sign in gamit GitHub account
3. Click "New app" → pilia ang imong repository ug `app.py` isip main file
4. Sa "Advanced settings" → "Secrets", idugang ni:
   ```toml
   GEMINI_API_KEY = "ang-imong-actual-api-key-dinhi"
   ```
5. Click "Deploy"

Pagkahuman, makuha ka og public URL nga pwede i-share o gamiton bisan asa (pwede gamiton bisan sa phone browser).

## Lokal nga Pag-run (Optional, para sa testing una)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Pagka-open sa browser (auto), i-paste ang imong API key sa sidebar (kay wala pay secrets sa lokal nga setup, gawas kung gumawa ka og `.streamlit/secrets.toml`).

## Bantayi
- Free tier sa Gemini API naay rate limits (limited requests per minute). Sakto ra ni para personal/classroom use.
- Ang AI-generated content kinahanglan pa gihapon susihon/i-edit base sa actual nga klase ug curriculum guide.
