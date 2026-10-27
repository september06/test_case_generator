import os
import json 
from dotenv import load_dotenv 
from openai import OpenAI
import sys
import re
import gradio as gr

# בדיקת ספריות
try:
    import pandas as pd
    print("✅ pandas imported successfully")
except ImportError:
    print("❌ Error: 'pandas' module not found.")
    print("💡 Install with: pip install pandas")
    sys.exit(1)

try:
    from docx import Document
    print("✅ python-docx imported successfully")
except ImportError:
    print("❌ Error: 'python-docx' module not found.")
    print("💡 Install with: pip install python-docx")
    sys.exit(1)

load_dotenv(override=True)
GOOGLE_KEY = os.getenv('GEMINI_API_KEY')
MODEL = "gemini-2.5-flash"

openai = OpenAI(
    api_key=GOOGLE_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

class Get_document:
    def __init__(self, file_path):
        self.file_path = file_path

    def get_text_from_file(self):
        """Reads the content of the .docx file if it exists
           and extracts the paragraphs as a list of strings"""
        if not self.file_path or not os.path.exists(self.file_path):
            return ""
        try:
            doc = Document(self.file_path)
            paragraphs_list_as_text = []
            for para in doc.paragraphs:
                if para.text.strip():
                    paragraphs_list_as_text.append(para.text)
            return "\n".join(paragraphs_list_as_text)
        except Exception as e:
            print(f"An error occurred: {e}")
            return ""

req_doc_system_prompt = (
    "You are provided with a complete requirements specifications document. "
    "Identify each requirement as functional or non-functional and list them all. "
    "Respond ONLY in JSON format as: "
    "{\"requirements\": [{\"RequirementNo\": \"FR-01\", \"Requirement Description\": \"...\"}]}"
)

def req_doc_user_prompt(text_content):
    user_prompt = "Here is the contents from a requirement document.\n"
    user_prompt += f"{text_content} \n"
    user_prompt += "Please scan through the document and extract only the actual requirements. "
    user_prompt += "You must respond in a JSON format."
    return user_prompt[:25_000]

def get_test_system_prompt():
    return (
        "You are an expert QA engineer that receives a list of functional and non-functional requirements in JSON format. "
        "Generate detailed unit test cases for each requirement in a table and order it by requirement No. "
        "Output the result ONLY as a Markdown Table with these exact columns: "
        "| S No | Requirement No | Requirement Description | Test Case ID | Test Case Summary | Test Case Description | Success Criteria |"
    )

def get_test_user_prompt(parsed_requirements):
    user_prompt = "You are looking at the following list of requirements. \n"
    user_prompt += f"{json.dumps(parsed_requirements, ensure_ascii=False)}\n"
    user_prompt += "Prepare unit test cases for each of these requirements in a table and send that table as response. \n"
    return user_prompt[:25000]

# הפונקציה השנייה - מייצרת את ה-Test Cases ומזרימה למסך
def create_testcase_gradio(parsed_requirements):
    try:
        stream = openai.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": get_test_system_prompt()},
                {"role": "user", "content": get_test_user_prompt(parsed_requirements)}
            ],
            stream=True
        )
        
        result = ""
        for chunk in stream:
            result += chunk.choices[0].delta.content or ""
            excel_path = export_markdown_table_to_excel(result)
            yield result, excel_path
            
    except Exception as e:
        yield f"❌ שגיאה ביצירת מקרי הבדיקה: {str(e)}", None

# הפונקציה הראשית שמנהלת את התהליך
def process_requirements_and_generate_tests(file_path):
    if not file_path:
        yield "please check file path", None
        return
        
    reqdoc = Get_document(file_path)
    text = reqdoc.get_text_from_file()
    
    if not text.strip():
        yield "Empty file !!", None
        return
        
    try:
        response = openai.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": req_doc_system_prompt},
                {"role": "user", "content": req_doc_user_prompt(text)}
            ],
            response_format={"type": "json_object"}
        )
        requirements_data = response.choices[0].message.content
    except Exception as e:
        yield f"Something Wrong {str(e)}", None
        return
        
    yield "⏳ מעביר את הדרישות ליצירת Test Cases...", None
    parsed_requirements = json.loads(requirements_data)
    
    for markdown_res, excel_res in create_testcase_gradio(parsed_requirements):
        yield markdown_res, excel_res

def export_markdown_table_to_excel(markdown_text):
    lines = [line.strip() for line in markdown_text.split('\n') if line.strip().startswith('|')]
    if len(lines) < 3:
        return None
    headers = [col.strip() for col in lines[0].split('|')[1:-1]]
    data = []
    for line in lines[2:]:
        row = [col.strip() for col in line.split('|')[1:-1]]
        if len(row) == len(headers):
            data.append(row)

    if not data:
        return None

    df = pd.DataFrame(data, columns=headers)
    output_file = "test_cases.xlsx"
    df.to_excel(output_file, index=False)
    return output_file
# ממשק Gradio משודרג ומגניב
with gr.Blocks(theme=gr.themes.Glass()) as demo:
    # כותרת ראשית ממותגת AI
    gr.Markdown("# 🤖 AI-Powered QA Test Case Generator")
    gr.Markdown("###ואקסל ברגע Test Cases ל(.docx) ממיר מסמכי דרישות")
    
    with gr.Row():
        file_input = gr.File(label="📂 העלה מסמך דרישות (.docx)", file_types=[".docx"])
    
    with gr.Row():
        submit_btn = gr.Button("🚀 צור מקרי בדיקה באמצעות AI", variant="primary", scale=2)
    
    with gr.Tabs():
        with gr.TabItem("📊 טבלת מקרי בדיקה (Markdown)"):
            markdown_output = gr.Markdown(label="תוצאות בדיקה")
            
        with gr.TabItem("📥 הורדת קובץ"):
            with gr.Row():
                excel_output = gr.File(label="הורד קובץ Excel מוכן (`test_cases.xlsx`)", visible=True)

    # חיבור הכפתור לפונקציה
    submit_btn.click(
        fn=process_requirements_and_generate_tests,
        inputs=[file_input],
        outputs=[markdown_output, excel_output]
    )

demo.launch()