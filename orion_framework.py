import os
import json
import time
import argparse
import openai
# from dotenv import load_dotenv # No longer needed when using Doppler
from supabase import create_client, Client
from openai import OpenAI
from abc import ABC, abstractmethod

# ==============================================================================
# IQSF GLOBAL QUEER SAFETY INDEX™ - METHODOLOGY
# ==============================================================================
METHODOLOGY = {
    "Legal Protections": [
        "Constitutional protections and equality provisions", "Anti-discrimination laws (employment, housing, services, education)",
        "Marriage and civil union recognition", "Adoption and parenting rights", "Gender recognition procedures and requirements",
        "Hate crime legislation and enforcement", "Military service policies", "Healthcare access protections",
        "Blood donation policies", "Asylum and refugee protections"
    ],
    "Social Attitudes": [
        "Public opinion polling on LGBTQ+ acceptance", "Religious and cultural attitudes", "Media representation and visibility",
        "Pride celebration safety and participation", "Public displays of affection acceptance", "Workplace inclusion attitudes",
        "Educational environment safety", "Family acceptance rates", "Generational attitude differences", "Urban vs. rural acceptance variations"
    ],
    "Healthcare Access": [
        "General healthcare system quality and accessibility", "LGBTQ+-affirming provider availability and training",
        "Gender-affirming care access and coverage", "Mental health services for LGBTQ+ individuals",
        "HIV/AIDS prevention, testing, and treatment", "Sexual health services and education", "Insurance coverage for LGBTQ+-related care",
        "Conversion therapy bans and protections", "Emergency healthcare non-discrimination", "Reproductive health access for LGBTQ+ individuals"
    ],
    "Physical Safety": [
        "Hate crime rates and reporting", "Police responsiveness and competency", "General crime rates and safety conditions",
        "Domestic violence protections and services", "Safe spaces and community centers", "School safety and anti-bullying policies",
        "Workplace harassment protections", "Public transportation safety", "Tourism safety for LGBTQ+ visitors", "Emergency response effectiveness"
    ],
    "Economic Opportunities": [
        "Workplace discrimination protections", "Economic inclusion initiatives", "LGBTQ+ business support and networking",
        "Access to financial services", "Housing discrimination protections", "Educational opportunity equality",
        "Professional advancement barriers", "Entrepreneurship support", "Government employment policies", "Corporate diversity and inclusion"
    ],
    "Community Support": [
        "LGBTQ+ organization presence and strength", "Community center availability", "Support group accessibility",
        "Advocacy organization effectiveness", "Peer support network strength", "Online community access and safety",
        "Intergenerational support systems", "Crisis intervention services", "Cultural and social event availability",
        "Volunteer and activism opportunities"
    ]
}

# ==============================================================================
# --- 1. CORE FRAMEWORK: THE ABSTRACT AGENT ---
# ==============================================================================

class Agent(ABC):
    """Abstract base class for all IQSF agents."""
    def __init__(self):
        print(f"\n--- Initializing {self.__class__.__name__} ---")
        self.supabase, self.openai = self._setup_connections()

    def _setup_connections(self):
        """Loads environment variables directly from the environment (injected by Doppler)."""
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY")
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not all([url, key, openai_api_key]):
            raise EnvironmentError("Supabase or OpenAI credentials not found. Ensure Doppler is running.")
        
        supabase_client = create_client(url, key)
        openai_client = OpenAI(api_key=openai_api_key)
        print("-> Connections established.")
        return supabase_client, openai_client

    @abstractmethod
    def run(self, **kwargs):
        pass

# ==============================================================================
# --- 2. CONCRETE AGENTS: THE WORKERS ---
# ==============================================================================

class PlannerAgent(Agent):
    """Creates a new research plan for a country based on the methodology."""
    def _generate_questions(self, country_name: str, dimension: str, sub_points: list) -> list:
        print(f"  -> Generating questions for dimension: '{dimension}'...")
        prompt = f"""
        You are an IQSF Index Analyst generating Key Research Questions (KRQs) for **{country_name}** for the **'{dimension}'** dimension.
        Your analysis MUST be intersectional. For each sub-point, consider how the issue might differ for various identities within the LGBTQIA+ coalition.
        Based on these sub-points: {json.dumps(sub_points)}.
        Return a JSON object: {{"key_research_questions": ["..."]}}
        """
        try:
            response = self.openai.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[{"role": "system", "content": "You are a research strategist..."}, {"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content).get("key_research_questions", [])
        except Exception as e:
            print(f"    -> Error generating questions: {e}")
            return []

    def run(self, country: str, pillar_id: int = 3):
        print(f"-> Starting research plan for {country}.")
        response = self.supabase.rpc('create_new_report', {'country_name_input': country, 'pillar_id_input': pillar_id}).execute()
        report_id = response.data
        if not report_id:
            print("-> ERROR: Failed to create report entry. Aborting.")
            return

        print(f"-> Report entry created with ID: {report_id}")
        all_questions = []
        for dimension, sub_points in METHODOLOGY.items():
            questions = self._generate_questions(country, dimension, sub_points)
            all_questions.extend(questions)
        
        if all_questions:
            self.supabase.table('research_questions').insert([{"report_id": report_id, "question": q} for q in all_questions]).execute()
            print(f"-> SUCCESS: Saved {len(all_questions)} questions for Report ID {report_id}.")
        else:
            self.supabase.table('reports').update({"status": "PLAN_FAILED"}).eq("id", report_id).execute()
            print("-> ERROR: Failed to generate any questions.")

class GathererAgent(Agent):
    """Finds evidence for pending research questions continuously."""
    def _find_evidence(self, question_text: str) -> dict:
        print(f"  -> Researching: '{question_text}'")
        prompt = f"""
        You are an AI Research Agent. Search your knowledge to answer the following specific question.
        Your response MUST be a single, valid JSON object and nothing else.
        Research Question: "{question_text}"
        JSON Structure: {{ "question": "{question_text}", "answer_summary": "...", "key_findings": ["..."], "sources": [{{"url": "...", "title": "...", "organization": "...", "quote": "..."}}] }}
        """
        try:
            response = self.openai.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[{"role": "system", "content": "You are a highly advanced AI Research Agent..."}, {"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"    -> OpenAI Error: {e}")
            return None

    def run(self):
        print("-> Starting continuous evidence gathering. Press Ctrl+C to stop.")
        while True:
            response = self.supabase.rpc('get_next_unanswered_question').execute()
            question = response.data[0] if response.data else None
            
            if not question:
                print("-> No pending questions found. Worker will now exit.")
                break
            
            question_id = question['id']
            evidence = self._find_evidence(question['question'])
            
            if evidence:
                evidence.pop('question', None)
                evidence['question_id'] = question_id
                save_response = self.supabase.table('evidence_items').insert(evidence).execute()
                
                if save_response.data:
                    self.supabase.table('research_questions').update({'status': 'COMPLETE'}).eq('id', question_id).execute()
                    print(f"  -> SUCCESS: Processed question {question_id}.")
                else:
                    self.supabase.table('research_questions').update({'status': 'SAVE_FAILED'}).eq('id', question_id).execute()
                    print(f"  -> FAILED: Could not save evidence for question {question_id}.")
            else:
                self.supabase.table('research_questions').update({'status': 'RESEARCH_FAILED'}).eq('id', question_id).execute()
                print(f"  -> FAILED: Could not find evidence for question {question_id}.")

class ScoringAgent(Agent):
    """Analyzes evidence and generates an IQSF Index Score Card."""
    def _generate_score_card(self, country_name: str, all_evidence: list) -> dict:
        print("  -> Beginning AI scoring process (this may take 30-90 seconds)...")
        prompt = f"""
        You are an IQSF Index Analyst. Generate the official, multi-axis Global Queer Safety Index™ score card for **{country_name}**.
        Your analysis MUST be intersectional. Review the provided evidence and assign separate scores for each identity axis (Gay/Lesbian, Transgender, etc.) within each dimension.
        Your output MUST be a single, valid JSON object.
        **VERIFIED EVIDENCE:**
        {json.dumps(all_evidence, indent=2)}
        **JSON OUTPUT STRUCTURE:**
        {{ "country": "{country_name}", "overall_weighted_score": "[...]", "score_matrix": {{ "legal_protections": {{ "overall_score": "[...]", "justification": "...", "identity_scores": {{...}} }} }} }}
        """
        try:
            response = self.openai.chat.completions.create(
                model="gpt-4-turbo", messages=[{"role": "system", "content": "You are a Senior IQSF Index Analyst..."}, {"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"  -> Error during AI scoring: {e}")
            return None

    def run(self):
        print("-> Searching for completed report to score...")
        response = self.supabase.rpc('get_next_report_for_synthesis').execute()
        report = response.data[0] if response.data else None
        if not report:
            print("-> No reports ready for scoring.")
            return

        report_id, country_name = report['id'], report['country_name']
        print(f"-> Found report: ID {report_id}, Country: {country_name}")
        
        evidence_response = self.supabase.rpc('get_all_evidence_for_report', {'report_id_input': report_id}).execute()
        evidence = evidence_response.data
        if not evidence:
            print(f"-> ERROR: No evidence found for report {report_id}. Marking as failed.")
            self.supabase.table('reports').update({'status': 'SCORING_FAILED'}).eq('id', report_id).execute()
            return
        
        score_card = self._generate_score_card(country_name, evidence)
        if score_card:
            self.supabase.table('index_scores').insert({'report_id': report_id, 'country_name': country_name, 'final_score': score_card.get('overall_weighted_score'), 'score_data': score_card.get('score_matrix')}).execute()
            self.supabase.table('reports').update({'status': 'REVIEW'}).eq('id', report_id).execute()
            print(f"-> SUCCESS: Report ID {report_id} is now in 'REVIEW' status.")
        else:
            self.supabase.table('reports').update({'status': 'SCORING_FAILED'}).eq('id', report_id).execute()

class NarrativeAgent(Agent):
    """Generates a final, human-readable narrative report."""
    def _generate_narrative(self, country_name: str, score_card: dict, all_evidence: list) -> str:
        print("  -> Beginning AI narrative generation (this may take 30-60 seconds)...")
        prompt = f"""
        You are an expert analyst and writer for the IQSF. Write a detailed, 2000-word narrative report for the IQSF Global Queer Safety Index™ on **{country_name}**.
        Tell the story BEHIND the numbers, weaving evidence into a compelling narrative and paying special attention to intersectional differences.
        **FINAL SCORE CARD:**
        {json.dumps(score_card, indent=2)}
        **RAW EVIDENCE:**
        {json.dumps(all_evidence, indent=2)}
        The output should be only the final article text in Markdown format.
        """
        try:
            response = self.openai.chat.completions.create(model="gpt-4-turbo", messages=[{"role": "system", "content": "You are an expert IQSF analyst..."}, {"role": "user", "content": prompt}])
            return response.choices[0].message.content
        except Exception as e:
            print(f"  -> Error during AI narrative generation: {e}")
            return None

    def run(self):
        print("-> Searching for scored report to narrate...")
        response = self.supabase.table('reports').select('id, country_name').eq('status', 'REVIEW').limit(1).single().execute()
        report = response.data
        if not report:
            print("-> No reports ready for narrative generation.")
            return

        report_id, country_name = report['id'], report['country_name']
        print(f"-> Found report to narrate: ID {report_id}, Country: {country_name}")
        
        evidence = self.supabase.rpc('get_all_evidence_for_report', {'report_id_input': report_id}).execute().data
        score_card = self.supabase.table('index_scores').select('*').eq('report_id', report_id).single().execute().data
        
        if evidence and score_card:
            narrative = self._generate_narrative(country_name, score_card, evidence)
            if narrative:
                self.supabase.table('published_content').upsert({'report_id': report_id, 'final_article_text': narrative}, on_conflict='report_id').execute()
                self.supabase.table('reports').update({'status': 'COMPLETE'}).eq('id', report_id).execute()
                print(f"-> SUCCESS: Report ID {report_id} is now 'COMPLETE'.")

class CurriculumDeveloperAgent(Agent):
    """Transforms finished reports into educational course content."""
    def _generate_course_blueprint(self, report_narrative: str, country_name: str) -> dict:
        print(f"  -> Generating course blueprint for {country_name}...")
        prompt = f"""
        You are an expert Instructional Designer. Transform the following intelligence report on **{country_name}** into a blueprint for a Skool mini-course.
        Generate a JSON object with: Course Title, Learning Objectives, Module Breakdown (with titles and descriptions), and a Downloadable Asset Idea.
        **Source Intelligence Report:** --- {report_narrative} ---
        """
        try:
            response = self.openai.chat.completions.create(model="gpt-4-turbo-preview", messages=[{"role": "system", "content": "You are an Instructional Designer..."}, {"role": "user", "content": prompt}], response_format={"type": "json_object"})
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"  -> Error generating course blueprint: {e}")
            return None

    def run(self, report_id: int):
        print(f"-> Starting curriculum development for Report ID: {report_id}")
        response = self.supabase.table('published_content').select('final_article_text, reports(country_name)').eq('report_id', report_id).single().execute()
        if not response.data:
            print(f"-> ERROR: No published content found for Report ID {report_id}.")
            return

        narrative = response.data['final_article_text']
        country_name = response.data['reports']['country_name']
        course_plan = self._generate_course_blueprint(narrative, country_name)
        
        if course_plan:
            print("\n--- COURSE BLUEPRINT GENERATED ---")
            print(json.dumps(course_plan, indent=2))
        else:
            print("-> FAILED: Could not generate course blueprint.")

class AcademicReportAgent(Agent):
    """Transforms a standard narrative report into a formal, academic-style paper."""
    def _generate_academic_paper(self, country_name: str, narrative_report: str, score_card: dict, evidence: list) -> str:
        print("  -> Generating academic paper (this may take 60-120 seconds)...")
        source_urls = list(set([s['url'] for item in evidence if 'sources' in item and item['sources'] for s in item['sources'] if 'url' in s]))
        prompt = f"""
        You are a Ph.D.-level academic researcher. Transform the provided IQSF report on **{country_name}** into a formal academic paper.
        Structure it with: Abstract, Introduction, Literature Review, Methodology, Findings & Analysis (by pillar), Discussion, Conclusion, and Bibliography.
        **Source Narrative:** --- {narrative_report} ---
        **Source Score Card:** --- {json.dumps(score_card, indent=2)} ---
        **Bibliography URLs:** --- {json.dumps(source_urls, indent=2)} ---
        """
        try:
            response = self.openai.chat.completions.create(model="gpt-4-turbo", messages=[{"role": "system", "content": "You are a Ph.D.-level academic writer..."}, {"role": "user", "content": prompt}])
            return response.choices[0].message.content
        except Exception as e:
            print(f"    -> Error generating academic paper: {e}")
            return None

    def run(self, report_id: int):
        print(f"-> Starting academic paper generation for Report ID: {report_id}")
        narrative_response = self.supabase.table('published_content').select('final_article_text, reports(country_name)').eq('report_id', report_id).single().execute()
        score_card_response = self.supabase.table('index_scores').select('*').eq('report_id', report_id).single().execute()
        evidence_response = self.supabase.rpc('get_all_evidence_for_report', {'report_id_input': report_id}).execute()

        if not (narrative_response.data and score_card_response.data and evidence_response.data):
            print(f"-> ERROR: Could not retrieve all necessary data for Report ID {report_id}.")
            return

        narrative, country_name = narrative_response.data['final_article_text'], narrative_response.data['reports']['country_name']
        score_card, evidence = score_card_response.data, evidence_response.data
        academic_paper = self._generate_academic_paper(country_name, narrative, score_card, evidence)
        
        if academic_paper:
            filename = f"IQSF_Academic_Paper_Report_{report_id}_{country_name}.md"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(academic_paper)
            print(f"\n-> SUCCESS! Academic paper saved to: {filename}")
        else:
            print("-> FAILED: Could not generate academic paper.")

# ==============================================================================
# --- 3. MAIN COMMAND-LINE INTERFACE ---
# ==============================================================================
def main():
    """Parses command-line arguments and runs the appropriate agent."""
    parser = argparse.ArgumentParser(description="Master Controller for the IQSF Intelligence Factory.")
    subparsers = parser.add_subparsers(dest='agent', required=True, help='The agent to run.')

    plan_parser = subparsers.add_parser('plan', help='Run the Planner Agent.')
    plan_parser.add_argument('-c', '--country', type=str, required=True, help='The country to research.')
    
    subparsers.add_parser('gather', help='Run the Gatherer Agent continuously.')
    subparsers.add_parser('score', help='Run the Scoring Agent on a completed report.')
    subparsers.add_parser('narrate', help='Generate the final narrative for a scored report.')
    
    curriculum_parser = subparsers.add_parser('curriculum', help='Run the Curriculum Developer Agent.')
    curriculum_parser.add_argument('-r', '--report_id', type=int, required=True, help='The ID of the report to transform.')

    academic_parser = subparsers.add_parser('academic', help='Run the Academic Report Agent.')
    academic_parser.add_argument('-r', '--report_id', type=int, required=True, help='The ID of the report to transform.')

    args = parser.parse_args()

    # Agent Factory
    agent_map = {
        'plan': (PlannerAgent, {'country': args.country}),
        'gather': (GathererAgent, {}),
        'score': (ScoringAgent, {}),
        'narrate': (NarrativeAgent, {}),
        'curriculum': (CurriculumDeveloperAgent, {'report_id': args.report_id}),
        'academic': (AcademicReportAgent, {'report_id': args.report_id}),
    }

    if args.agent in agent_map:
        AgentClass, kwargs = agent_map[args.agent]
        agent = AgentClass()
        agent.run(**kwargs)
    else:
        print(f"Error: Unknown agent '{args.agent}'")

if __name__ == "__main__":
    main()
