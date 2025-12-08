import customtkinter as ctk
import json
import os
import sys
import unicodedata
import re
from typing import List, Dict, Any, Optional
from PIL import Image

# =========================================================
# 1. FUNCIÓN MÁGICA PARA RECURSOS (Imágenes/Iconos)
# =========================================================
def resource_path(relative_path):
    """ Obtiene la ruta absoluta al recurso, funciona para dev y para PyInstaller """
    try:
        # PyInstaller crea una carpeta temporal en _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# =========================================================
# 2. LÓGICA DEL SISTEMA EXPERTO (BACKEND)
# =========================================================

DB_FILENAME = "OBD2 DATASET.JSON"

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

class TextProcessor:
    @staticmethod
    def normalize(text: str) -> str:
        if not isinstance(text, str): return ""
        text = text.lower()
        text = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('utf-8')
        text = re.sub(r'[^a-z0-9\s]', '', text)
        return re.sub(r'\s+', ' ', text).strip()

class KnowledgeBase:
    def __init__(self, filename: str):
        self.filename = filename
        self.data: List[Dict] = []
        self.index_by_code: Dict[str, Dict] = {}
        self._load_data()

    def _load_data(self):
        # Intentamos cargar el JSON. Si estamos en exe, el json debe estar AL LADO del exe.
        # No usamos resource_path aquí porque el JSON es externo/editable.
        if not os.path.exists(self.filename):
            # No podemos imprimir error en consola si es noconsole, pero fallará silenciosamente
            # O idealmente mostrar un popup de error.
            return
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
            for entry in self.data:
                code = entry.get('codigo', entry.get('code', '')).strip().upper()
                if code: self.index_by_code[code] = entry
        except Exception as e:
            pass

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
# 3. INTERFAZ GRÁFICA ESTILO "HERO" (FRONTEND)
# =========================================================

ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

class DashboardApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- SETUP VENTANA ---
        self.title("Sistema Experto Automotriz")
        self.geometry("1200x750")
        
        # Cargar Motor
        self.kb = KnowledgeBase(DB_FILENAME)
        self.engine = InferenceEngine(self.kb)

        # Variables Flujo
        self.symptoms_history = []
        self.step_counter = 1
        self.symptoms_left = 3

        # --- CARGA DE IMAGEN HERO (CORREGIDO) ---
        # AQUI ESTABA EL ERROR: Ahora usamos resource_path
        image_path = resource_path("motor_hero.png")
        
        self.hero_image = None
        if os.path.exists(image_path):
            self.hero_image = ctk.CTkImage(Image.open(image_path), size=(850, 750))
        else:
            print(f"Advertencia: No se encontró la imagen en {image_path}")

        # --- GRID PRINCIPAL ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Marco Principal
        self.main_frame = ctk.CTkFrame(self, fg_color="#EBF2F7", corner_radius=0)
        self.main_frame.grid(row=0, column=0, sticky="nsew")
        
        # Grid del Main Frame
        self.main_frame.grid_columnconfigure(0, weight=4) 
        self.main_frame.grid_columnconfigure(1, weight=6) 
        self.main_frame.grid_rowconfigure(0, weight=1)

        # Iniciar Vistas
        self.show_home_hero()

    def clear_screen(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()

    # ---------------------------------------------------------
    # VISTA 1: HOME PAGE
    # ---------------------------------------------------------
    def show_home_hero(self):
        self.clear_screen()

        # --- COLUMNA IZQUIERDA ---
        left_panel = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(60, 20), pady=40)

        # Título
        title_font = ctk.CTkFont(family="Arial", size=48, weight="bold")
        ctk.CTkLabel(left_panel, text="Sistema Experto\nAutomotriz", 
                     font=title_font, text_color="#0F172A", justify="left").pack(anchor="w", pady=(60, 20))

        # Subtítulo
        sub_font = ctk.CTkFont(family="Arial", size=18)
        ctk.CTkLabel(left_panel, text="Diagnóstico inteligente y rápido de\ncódigos DTC OBD-II e interpretación de síntomas.", 
                     font=sub_font, text_color="#475569", justify="left").pack(anchor="w", pady=(0, 40))

        # Barra de Búsqueda
        search_container = ctk.CTkFrame(left_panel, fg_color="white", corner_radius=30, height=60)
        search_container.pack(anchor="w", fill="x", pady=(0, 20))
        search_container.pack_propagate(False)

        self.entry_code_home = ctk.CTkEntry(search_container, placeholder_text="Ej: P0300", 
                                            border_width=0, fg_color="transparent", 
                                            font=("Arial", 16), text_color="#333")
        self.entry_code_home.pack(side="left", padx=20, fill="x", expand=True)

        ctk.CTkButton(search_container, text="BUSCAR", width=100, height=40, corner_radius=20,
                      fg_color="#8EA7E9", hover_color="#7289DA", font=("Arial", 14, "bold"), 
                      command=self.perform_quick_search).pack(side="right", padx=10)

        # Navegación
        nav_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        nav_frame.pack(anchor="w", pady=10)

        ctk.CTkButton(nav_frame, text="Buscar Código", fg_color="transparent", 
                      text_color="#0F172A", font=("Arial", 14, "bold", "underline"), hover=False,
                      anchor="w", command=lambda: None).pack(side="left", padx=(0, 20))

        ctk.CTkButton(nav_frame, text="Diagnóstico Guiado", fg_color="transparent", 
                      text_color="#64748B", font=("Arial", 14), hover_color="#E2E8F0",
                      anchor="w", command=self.show_symptoms_view).pack(side="left")

        # --- COLUMNA DERECHA ---
        right_panel = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=20, pady=40)

        if self.hero_image:
            ctk.CTkLabel(right_panel, text="", image=self.hero_image).place(relx=0.5, rely=0.5, anchor="center")
        else:
            ctk.CTkLabel(right_panel, text="[PONER IMAGEN 'motor_hero.png']", font=("Arial", 20), text_color="gray").place(relx=0.5, rely=0.5, anchor="center")

    # ---------------------------------------------------------
    # LÓGICA DE BÚSQUEDA RÁPIDA
    # ---------------------------------------------------------
    def perform_quick_search(self):
        code = self.entry_code_home.get().strip()
        if not code: return
        self.show_results_modal(code)

    def show_results_modal(self, code):
        res = self.engine.diagnose_by_code(code)
        
        modal = ctk.CTkToplevel(self)
        modal.title(f"Reporte: {code}")
        modal.geometry("600x600")
        modal.attributes("-topmost", True)

        scroll = ctk.CTkScrollableFrame(modal, fg_color="white")
        scroll.pack(fill="both", expand=True, padx=20, pady=20)

        if not res["found"]:
            ctk.CTkLabel(scroll, text="❌ Código no encontrado", font=("Arial", 20, "bold"), text_color="red").pack(pady=20)
        else:
            ctk.CTkLabel(scroll, text=f"Código: {res['code']}", font=("Arial", 24, "bold"), text_color="#2A2D9E").pack(anchor="w")
            ctk.CTkLabel(scroll, text=res['description'], font=("Arial", 16), text_color="#333", justify="left").pack(anchor="w", pady=(0, 10))
            
            self.create_info_block(scroll, "SEVERIDAD", res['severity'], "red" if "ALTA" in str(res['severity']) else "orange")
            self.create_info_block(scroll, "SISTEMA", res['system'], "blue")
            
            if res['causes']:
                ctk.CTkLabel(scroll, text="Causas Probables:", font=("Arial", 14, "bold"), text_color="#333").pack(anchor="w", pady=(10, 5))
                for c in res['causes']:
                    ctk.CTkLabel(scroll, text=f"• {c}", text_color="#555", anchor="w", justify="left").pack(anchor="w")

            if res['solutions']:
                ctk.CTkLabel(scroll, text="Soluciones:", font=("Arial", 14, "bold"), text_color="#333").pack(anchor="w", pady=(10, 5))
                for s in res['solutions']:
                    ctk.CTkLabel(scroll, text=f"✓ {s}", text_color="#555", anchor="w", justify="left").pack(anchor="w")

    def create_info_block(self, parent, title, value, color):
        f = ctk.CTkFrame(parent, fg_color="#F3F4F6", corner_radius=5)
        f.pack(fill="x", pady=5)
        ctk.CTkLabel(f, text=f"{title}: {value}", font=("Arial", 12, "bold"), text_color=color).pack(padx=10, pady=5, anchor="w")

    # ---------------------------------------------------------
    # VISTA 2: SÍNTOMAS
    # ---------------------------------------------------------
    def show_symptoms_view(self):
        self.clear_screen()
        
        self.symptoms_history = []
        self.step_counter = 1
        self.symptoms_left = 3

        container = ctk.CTkFrame(self.main_frame, fg_color="white", corner_radius=20, width=900, height=650)
        container.place(relx=0.5, rely=0.5, anchor="center")
        container.pack_propagate(False)

        ctk.CTkLabel(container, text="Diagnóstico Guiado", font=("Arial", 24, "bold"), text_color="#2A2D9E").pack(pady=(30, 5))
        self.lbl_step = ctk.CTkLabel(container, text="PASO 1/3: Seleccione un síntoma", font=("Arial", 16), text_color="#555")
        self.lbl_step.pack(pady=5)
        
        self.lbl_counter = ctk.CTkLabel(container, text="Restantes: 3", font=("Arial", 12), text_color="gray")
        self.lbl_counter.pack(pady=(0, 20))

        options_frame = ctk.CTkFrame(container, fg_color="transparent")
        options_frame.pack(padx=50, fill="both", expand=True)

        common_symptoms = [
            "Humo Negro", "Humo Azul", "No Arranca", "Se Apaga",
            "Jaloneos", "Vibración", "Falta Potencia", "Alto Consumo", 
            "Calentamiento", "Olor Gasolina", "Ralentí Inestable", "Ruido Motor"
        ]
        
        self.symptom_var = ctk.StringVar(value="")
        
        for i, sym in enumerate(common_symptoms):
            ctk.CTkRadioButton(options_frame, text=sym, variable=self.symptom_var, value=sym, 
                               font=("Arial", 14), text_color="#333", border_color="#8EA7E9", hover_color="#8EA7E9").grid(row=i//3, column=i%3, padx=20, pady=15, sticky="w")

        self.entry_extra = ctk.CTkEntry(container, placeholder_text="O escriba otro síntoma...", width=300)
        self.entry_extra.pack(pady=10)

        actions_frame = ctk.CTkFrame(container, fg_color="transparent")
        actions_frame.pack(pady=30, fill="x", padx=50)

        ctk.CTkButton(actions_frame, text="← Volver", fg_color="transparent", text_color="gray", hover=False, command=self.show_home_hero).pack(side="left")
        
        self.btn_finish = ctk.CTkButton(actions_frame, text="VER RESULTADOS", fg_color="#6C5CE7", width=150, command=self.finish_diagnosis)
        self.btn_finish.pack(side="right", padx=10)

        self.btn_add = ctk.CTkButton(actions_frame, text="AGREGAR SÍNTOMA", fg_color="#8EA7E9", width=150, command=self.next_step_logic)
        self.btn_add.pack(side="right")

    def next_step_logic(self):
        sym = self.symptom_var.get()
        extra = self.entry_extra.get().strip()
        final = extra if extra else sym

        if not final: return

        self.symptoms_history.append(final)
        self.symptoms_left -= 1
        self.step_counter += 1
        
        self.lbl_counter.configure(text=f"Restantes: {max(0, self.symptoms_left)}")
        self.symptom_var.set("")
        self.entry_extra.delete(0, 'end')

        if self.step_counter > 3:
            self.finish_diagnosis()
        else:
            self.lbl_step.configure(text=f"PASO {self.step_counter}/3: Seleccione otro síntoma")

    def finish_diagnosis(self):
        if not self.symptoms_history: return
        query = " ".join(self.symptoms_history)
        results = self.engine.diagnose_by_symptoms(query)
        
        modal = ctk.CTkToplevel(self)
        modal.title("Resultados")
        modal.geometry("700x600")
        modal.attributes("-topmost", True)

        scroll = ctk.CTkScrollableFrame(modal, fg_color="white")
        scroll.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(scroll, text=f"Basado en: {', '.join(self.symptoms_history)}", font=("Arial", 14, "italic"), text_color="#555").pack(pady=10)

        if not results:
            ctk.CTkLabel(scroll, text="No se encontraron coincidencias.", text_color="red").pack()
        else:
            for r in results[:5]:
                f = ctk.CTkFrame(scroll, fg_color="#F8FAFC", corner_radius=10, border_width=1, border_color="#E2E8F0")
                f.pack(fill="x", pady=5, padx=5)
                
                ctk.CTkLabel(f, text=f"{r['code']} ({int(r['score'])} pts)", font=("Arial", 16, "bold"), text_color="#2A2D9E").pack(anchor="w", padx=10, pady=(10,0))
                ctk.CTkLabel(f, text=r['description'], text_color="#333", justify="left").pack(anchor="w", padx=10)
                
                if r['causes']:
                    ctk.CTkLabel(f, text=f"Causa: {r['causes'][0]}", text_color="#666", font=("Arial", 12)).pack(anchor="w", padx=10, pady=(5,10))

if __name__ == "__main__":
    app = DashboardApp()
    app.mainloop()