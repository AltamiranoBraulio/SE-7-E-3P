import customtkinter as ctk
import json
import os
import sys
import unicodedata
import re
from typing import List, Dict, Any, Optional

# =========================================================
# LÓGICA DEL SISTEMA EXPERTO (BACKEND)
# =========================================================

DB_FILENAME = "OBD2 DATASET.JSON"

# DICCIONARIO DE SINÓNIMOS TÉCNICOS
TECHNICAL_SYNONYMS = {
    "humo negro": ["rica", "rich", "inyector", "presion combustible", "filtro aire"],
    "humo azul": ["aceite", "anillos", "valvula", "piston"],
    "humo blanco": ["refrigerante", "culata", "junta", "empaque", "agua"],
    "no arranca": ["bateria", "starter", "arranque", "bomba", "cigüeñal", "inmovilizador", "theft", "security"],
    "se apaga": ["ralenti", "iac", "vacio", "combustible", "sensor"],
    "jaloneos": ["misfire", "falla encendido", "bobina", "bujia", "inyector", "vacio"],
    "tiembla": ["soporte", "misfire", "balance", "cilindro", "ralenti"],
    "sin potencia": ["limp", "turbo", "catalizador", "obstruido", "maf", "presion", "fuerza"],
    "gasta gasolina": ["rica", "rich", "termostato", "sensor oxigeno", "fuga", "consumo"],
    "calienta": ["refrigerante", "termostato", "ventilador", "radiador", "bomba agua", "temperatura"],
    "freno duro": ["vacio", "booster", "manguera"],
    "olor gasolina": ["fuga", "evap", "canister", "tapon", "rica"],
    "vibra": ["misfire", "cilindro", "inyector", "bobina", "balance"]
}

SEVERITY_KEYWORDS = {
    "CRITICAL": ["overheat", "shut down", "no start", "immobilized", "theft", "sobrecalentamiento", "no arranca", "inmovilizado"],
    "HIGH": ["misfire", "module", "electrical", "fuel pressure", "short circuit", "falla de encendido", "modulo", "electrico", "corto", "baja presion"],
    "MEDIUM": ["trim", "vacuum leak", "sensor range", "performance", "mezcla", "fuga", "rango", "rendimiento"],
    "LOW": [] 
}

# ==========================================
# 1. CAPA DE UTILIDADES
# ==========================================

class TextProcessor:
    @staticmethod
    def normalize(text: str) -> str:
        if not isinstance(text, str): return ""
        text = text.lower()
        text = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('utf-8')
        text = re.sub(r'[^a-z0-9\s]', '', text)
        return re.sub(r'\s+', ' ', text).strip()

# ==========================================
# 2. CAPA DE ACCESO A DATOS
# ==========================================

class KnowledgeBase:
    def __init__(self, filename: str):
        self.filename = filename
        self.data: List[Dict] = []
        self.index_by_code: Dict[str, Dict] = {}
        self._load_data()

    def _load_data(self):
        if not os.path.exists(self.filename):
            print(f"ERROR: No se encontró '{self.filename}'.")
            return
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
            for entry in self.data:
                code = entry.get('codigo', entry.get('code', '')).strip().upper()
                if code: self.index_by_code[code] = entry
        except Exception as e:
            print(f"ERROR JSON: {e}")

    def get_entry_by_code(self, code: str) -> dict:
        return self.index_by_code.get(code.upper())

    def get_all_entries(self) -> List[Dict]:
        return self.data

class InferenceEngine:
    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def diagnose_by_code(self, code: str) -> Dict[str, Any]:
        raw = self.kb.get_entry_by_code(code)
        if not raw: return {"found": False, "code": code}
        processed = self._standardize(raw)
        processed["severity"] = self._infer_severity(processed)
        processed["warnings"] = self._generate_warnings(processed)
        processed["found"] = True
        return processed

    def diagnose_by_symptoms(self, user_input: str) -> List[Dict]:
        candidates = []
        norm_input = TextProcessor.normalize(user_input)
        search_terms = set(norm_input.split())
        expanded_terms = set(search_terms)
        
        for key, synonyms in TECHNICAL_SYNONYMS.items():
            if key in norm_input: 
                for syn in synonyms: expanded_terms.add(syn)

        final_keywords = [k for k in expanded_terms if len(k) > 2]
        if not final_keywords: return []

        for entry in self.kb.get_all_entries():
            proc = self._standardize(entry)
            score = 0.0
            matches = []
            record_text = (proc['description'] + " " + " ".join(proc['causes']) + " " + " ".join(proc['symptoms'])).lower()
            norm_record = TextProcessor.normalize(record_text)

            for term in final_keywords:
                if term in norm_record:
                    if term in TextProcessor.normalize(proc['description']):
                        score += 3.0
                        matches.append(f"Desc: {term}")
                    elif any(term in TextProcessor.normalize(s) for s in proc['symptoms']):
                        score += 2.5
                        matches.append(f"Sint: {term}")
                    elif any(term in TextProcessor.normalize(c) for c in proc['causes']):
                        score += 1.0
                        matches.append(f"Causa: {term}")
                    else:
                        score += 0.5

            if score > 0:
                proc["score"] = score
                proc["matches"] = list(set(matches))
                proc["severity"] = self._infer_severity(proc)
                proc["warnings"] = self._generate_warnings(proc)
                candidates.append(proc)

        candidates.sort(key=lambda x: x['score'], reverse=True)
        return candidates

    def _standardize(self, entry: Dict) -> Dict:
        return {
            "code": entry.get('codigo', entry.get('code', 'N/A')),
            "description": entry.get('descripcion', entry.get('description', 'N/A')),
            "system": entry.get('system', entry.get('sistema', 'General')),
            "causes": entry.get('causas_probables', entry.get('causes', [])),
            "solutions": entry.get('soluciones', entry.get('solutions', [])),
            "symptoms": entry.get('symptoms', entry.get('sintomas', [])),
            "brands": entry.get('brands', entry.get('marcas', [])),
            "severity": entry.get('severity', entry.get('severidad', None)),
            "drivability": entry.get('drivability', entry.get('conduccion', None))
        }

    def _infer_severity(self, data: Dict) -> str:
        if data['severity']: return data['severity']
        text = TextProcessor.normalize(f"{data['description']} {' '.join(data['causes'])}")
        for k in SEVERITY_KEYWORDS["CRITICAL"]: 
            if k in text: return "CRÍTICA"
        for k in SEVERITY_KEYWORDS["HIGH"]: 
            if k in text: return "ALTA"
        for k in SEVERITY_KEYWORDS["MEDIUM"]: 
            if k in text: return "MEDIA"
        return "BAJA"

    def _generate_warnings(self, data: Dict) -> List[str]:
        warns = []
        if data['brands']: warns.append(f"Específico para: {', '.join(data['brands'])}")
        if "CRÍTICA" in str(data['severity']) or "ALTA" in str(data['severity']):
            warns.append("PELIGRO: Detenga el vehículo.")
        return warns

# =========================================================
# INTERFAZ GRÁFICA MODERNA (FRONTEND - CUSTOMTKINTER)
# =========================================================

ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

class DashboardApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- SETUP ---
        self.title("Sistema Experto Automotriz")
        self.geometry("1100x700")
        
        # Cargar Motor
        self.kb = KnowledgeBase(DB_FILENAME)
        self.engine = InferenceEngine(self.kb)

        # Variables para el flujo iterativo de síntomas
        self.symptoms_history = []
        self.step_counter = 1
        self.symptoms_left = 3  # NUEVA VARIABLE PARA EL CONTADOR

        # Grid Principal
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- SIDEBAR (IZQUIERDA) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color="#2A2D9E")
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="🚗", font=ctk.CTkFont(size=60))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(40, 10))
        self.app_name = ctk.CTkLabel(self.sidebar_frame, text="AUTO EXPERT", font=ctk.CTkFont(size=20, weight="bold"), text_color="white")
        self.app_name.grid(row=1, column=0, padx=20, pady=10)

        self.btn_code = self.create_sidebar_button("Buscar Código", 2, command=self.show_code_search)
        self.btn_symptoms = self.create_sidebar_button("Diagnóstico Guiado", 3, command=self.show_symptoms_search)
        
        # --- MAIN AREA (DERECHA) ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#F0F0F0")
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        self.header_frame = ctk.CTkFrame(self.main_frame, height=60, corner_radius=0, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        self.lbl_header = ctk.CTkLabel(self.header_frame, text="Bienvenido", font=("Arial", 24, "bold"), text_color="#333")
        self.lbl_header.pack(side="left")

        self.content_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))

        self.show_code_search()

    def create_sidebar_button(self, text, row, command):
        btn = ctk.CTkButton(self.sidebar_frame, text=text, command=command,
                            fg_color="transparent", text_color=("gray90", "gray90"), hover_color="#1F2283",
                            height=50, anchor="w", font=("Arial", 14, "bold"))
        btn.grid(row=row, column=0, sticky="ew", padx=10, pady=5)
        return btn

    def clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    # ---------------------------------------------------------
    # VISTA 1: BÚSQUEDA POR CÓDIGO
    # ---------------------------------------------------------
    def show_code_search(self):
        self.clear_content()
        self.lbl_header.configure(text="Búsqueda Directa de DTC")

        card = ctk.CTkFrame(self.content_frame, fg_color="white", corner_radius=15)
        card.pack(fill="both", expand=True, padx=10, pady=10)

        input_frame = ctk.CTkFrame(card, fg_color="transparent")
        input_frame.pack(pady=30)
        
        self.entry_code = ctk.CTkEntry(input_frame, placeholder_text="Ej: P0300", width=300, height=40, font=("Arial", 16))
        self.entry_code.pack(side="left", padx=10)
        
        btn_search = ctk.CTkButton(input_frame, text="BUSCAR", width=120, height=40, fg_color="#6C5CE7", command=self.perform_code_search)
        btn_search.pack(side="left")

        self.txt_code_result = ctk.CTkTextbox(card, width=600, height=400, font=("Consolas", 14), fg_color="#FAFAFA", text_color="#333")
        self.txt_code_result.pack(pady=20, padx=20, fill="both", expand=True)
        self.txt_code_result.configure(state="disabled")

    def perform_code_search(self):
        code = self.entry_code.get().strip()
        if not code: return
        
        res = self.engine.diagnose_by_code(code)
        
        self.txt_code_result.configure(state="normal")
        self.txt_code_result.delete("0.0", "end")
        
        if not res["found"]:
            self.txt_code_result.insert("0.0", f"❌ Código {code} no encontrado.")
        else:
            report = f"✅ REPORTE: {res['code']}\n{'-'*60}\n"
            report += f"DESCRIPCIÓN: {res['description']}\n"
            report += f"SISTEMA:     {res['system']}\n"
            report += f"SEVERIDAD:   {res['severity']}\n"
            
            if res['warnings']:
                report += "\n⚠️ ADVERTENCIAS:\n" + "\n".join([f"  • {w}" for w in res['warnings']]) + "\n"
            
            report += "\n🔍 CAUSAS PROBABLES:\n" + "\n".join([f"  • {c}" for c in res['causes']]) + "\n"
            report += "\n🛠️ SOLUCIONES:\n" + "\n".join([f"  • {s}" for s in res['solutions']])
            
            self.txt_code_result.insert("0.0", report)
        
        self.txt_code_result.configure(state="disabled")

    # ---------------------------------------------------------
    # VISTA 2: DIAGNÓSTICO POR SÍNTOMAS (GUIADO)
    # ---------------------------------------------------------
    def show_symptoms_search(self):
        self.clear_content()
        self.lbl_header.configure(text="Diagnóstico Guiado (Paso a Paso)")
        
        # Resetear variables
        self.symptoms_history = []
        self.step_counter = 1
        self.symptoms_left = 3 # REINICIAMOS EL CONTADOR

        # Panel Izquierdo: Selección
        left_panel = ctk.CTkFrame(self.content_frame, fg_color="white", corner_radius=15, width=400)
        left_panel.pack(side="left", fill="y", padx=10, pady=10)

        self.lbl_step = ctk.CTkLabel(left_panel, text="PASO 1/3: Ingrese el síntoma principal", font=("Arial", 16, "bold"), text_color="#333")
        self.lbl_step.pack(pady=20, padx=20)

        # Opciones comunes (Checkboxes)
        self.scroll_cb = ctk.CTkScrollableFrame(left_panel, fg_color="transparent", height=200)
        self.scroll_cb.pack(fill="x", padx=10)

        common_symptoms = [
            "Humo Negro", "Humo Azul", "Humo Blanco", "No Arranca", "Se Apaga",
            "Jaloneos", "Vibración", "Falta Potencia", "Alto Consumo", 
            "Calentamiento", "Olor Gasolina", "Ralentí Inestable"
        ]
        
        self.symptom_var = ctk.StringVar(value="")
        
        for sym in common_symptoms:
            ctk.CTkRadioButton(self.scroll_cb, text=sym, variable=self.symptom_var, value=sym, text_color="#333").pack(anchor="w", pady=5)

        self.entry_extra = ctk.CTkEntry(left_panel, placeholder_text="O escriba otro síntoma...", width=250)
        self.entry_extra.pack(pady=10)

        self.btn_next = ctk.CTkButton(left_panel, text="AGREGAR SÍNTOMA", fg_color="#00B894", command=self.next_step)
        self.btn_next.pack(pady=10)
        
        # --- AQUÍ ESTÁ EL NUEVO CONTADOR ---
        self.lbl_counter = ctk.CTkLabel(left_panel, text=f"Espacios restantes: {self.symptoms_left}", font=("Arial", 14), text_color="gray")
        self.lbl_counter.pack(pady=5)
        # -----------------------------------

        self.btn_finish = ctk.CTkButton(left_panel, text="VER RESULTADOS AHORA", fg_color="#6C5CE7", command=self.finish_diagnosis)
        self.btn_finish.pack(pady=5)

        self.lbl_history = ctk.CTkLabel(left_panel, text="Historial: Ninguno", text_color="gray")
        self.lbl_history.pack(pady=20)

        # Panel Derecho: Resultados
        self.right_panel = ctk.CTkTextbox(self.content_frame, fg_color="white", text_color="#333", font=("Consolas", 12))
        self.right_panel.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        self.right_panel.configure(state="disabled")

    def next_step(self):
        symptom = self.symptom_var.get()
        extra = self.entry_extra.get().strip()
        final_symptom = extra if extra else symptom

        if not final_symptom: return

        self.symptoms_history.append(final_symptom)
        
        # Actualizar CONTADOR
        self.symptoms_left -= 1
        self.lbl_counter.configure(text=f"Espacios restantes: {max(0, self.symptoms_left)}")

        # Limpiar entradas
        self.symptom_var.set("")
        self.entry_extra.delete(0, 'end')

        # Actualizar UI
        self.lbl_history.configure(text=f"Historial: {', '.join(self.symptoms_history)}")
        
        query = " ".join(self.symptoms_history)
        results = self.engine.diagnose_by_symptoms(query)
        count = len(results)

        self.right_panel.configure(state="normal")
        self.right_panel.delete("0.0", "end")
        self.right_panel.insert("0.0", f"📊 ANÁLISIS PRELIMINAR:\nSe encontraron {count} posibles causas con los síntomas actuales.\n\n")
        
        if count > 0:
            top = results[0]
            self.right_panel.insert("end", f"Mejor candidato hasta ahora:\n[{top['code']}] {top['description']}\n")
        else:
            self.right_panel.insert("end", "⚠️ No hay coincidencias claras. Intente otro término.")

        self.right_panel.configure(state="disabled")

        self.step_counter += 1
        if self.step_counter > 3:
            self.finish_diagnosis()
        else:
            self.lbl_step.configure(text=f"PASO {self.step_counter}/3: Agregue más detalles")

    def finish_diagnosis(self):
        if not self.symptoms_history: return

        query = " ".join(self.symptoms_history)
        results = self.engine.diagnose_by_symptoms(query)

        self.right_panel.configure(state="normal")
        self.right_panel.delete("0.0", "end")

        header = f"🏁 DIAGNÓSTICO FINAL ({len(results)} coincidencias)\n{'='*60}\n\n"
        self.right_panel.insert("0.0", header)

        if not results:
            self.right_panel.insert("end", "No se encontraron resultados.")
        else:
            for idx, r in enumerate(results[:5], 1):
                block = f"#{idx} | CÓDIGO: {r['code']} | SCORE: {r['score']}\n"
                block += f"    DESC: {r['description']}\n"
                block += f"    SISTEMA: {r['system']}\n"
                
                if r['causes']:
                    block += f"    [?] CAUSA: {r['causes'][0]}\n"
                if r['solutions']:
                    block += f"    [+] SOLUCIÓN: {r['solutions'][0]}\n"
                
                if r.get('matches'):
                    unique_matches = list(set(r['matches']))
                    block += f"    (Coincidencia: {', '.join(unique_matches)})\n"

                block += "-"*60 + "\n"
                self.right_panel.insert("end", block)

        self.right_panel.configure(state="disabled")
        self.lbl_step.configure(text="Diagnóstico Completado")
        self.btn_next.configure(state="disabled")
        self.lbl_counter.configure(text="Espacios restantes: 0") # Asegurar que marque 0 al final

if __name__ == "__main__":
    app = DashboardApp()
    app.mainloop()