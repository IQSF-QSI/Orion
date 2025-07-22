import os
import json
import time
import argparse
import openai
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI
from abc import ABC, abstractmethod

# ==============================================================================
# --- 1. CORE FRAMEWORK: THE ABSTRACT AGENT ---
# ==============================================================================

class Agent(ABC):
    """
    An abstract base class for all agents in the IQSF factory.
    It defines the common structure and initialization.
    """
    def __init__(self):
        print(f"\n--- Initializing {self.__class__.__name__} ---")
        self.supabase, self.openai = self._setup_connections()

    def _setup_connections(self):
        """Loads environment variables and connects to services."""
        load_dotenv()
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY")
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not all([url, key, openai_api_key]):
            raise EnvironmentError("Supabase or OpenAI credentials not found.")
        
        supabase_client = create_client(url, key)
        openai_client = OpenAI(api_key=openai_api_key)
        print("-> Connections established.")
        return supabase_client, openai_client

    @abstractmethod
    def run(self, **kwargs):
        """
        The main execution method for the agent. This must be implemented by all subclasses.
        """
        pass

# ==============================================================================
# --- 2. CONCRETE AGENTS: THE WORKERS ---
# ==============================================================================

class PlannerAgent(Agent):
    """
    Agent responsible for creating a new research plan for a country.
    """
    METHODOLOGY = {
        "Legal Protections": ["Constitutional protections...", "Anti-discrimination laws..."],
        "Social Attitudes": ["Public opinion polling...", "Religious and cultural attitudes..."],
        # ... (full methodology here)
    }

    def _generate_questions(self, country_name: str, dimension: str, sub_points: list) -> list:
        print(f"  -> Generating questions for dimension: '{dimension}'...")
        prompt = f"""
        You are an IQSF Index Analyst. Generate Key Research Questions (KRQs) for **{country_name}** for the **'{dimension}'** dimension.
        Based on these sub-points: {json.dumps(sub_points)}.
        Your analysis MUST be intersectional. Return a JSON object: {{"key_research_questions": ["..."]}}
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
        for dimension, sub_points in self.METHODOLOGY.items():
            questions = self._generate_questions(country, dimension, sub_points)
            all_questions.extend(questions)
        
        if all_questions:
            self.supabase.table('research_questions').insert([{"report_id": report_id, "question": q} for q in all_questions]).execute()
            print(f"-> SUCCESS: Saved {len(all_questions)} questions for Report ID {report_id}.")
        else:
            self.supabase.table('reports').update({"status": "PLAN_FAILED"}).eq("id", report_id).execute()
            print("-> ERROR: Failed to generate any questions.")

class GathererAgent(Agent):
    """
    Agent responsible for finding evidence for pending research questions.
    Designed to run continuously.
    """
    def _find_evidence(self, question_text: str) -> dict:
        print(f"  -> Researching: '{question_text}'")
        prompt = f"You are an AI Research Agent... Research Question: \"{question_text}\"..." # (full prompt)
        try:
            response = self.openai.chat.completions.create(...) # (full call)
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
                print("-> No pending questions found. Waiting for 10 seconds.")
                time.sleep(10)
                continue
            
            question_id = question['id']
            evidence = self._find_evidence(question['question'])
            
            if evidence:
                evidence.pop('question', None)
                evidence['question_id'] = question_id
                self.supabase.table('evidence_items').insert(evidence).execute()
                self.supabase.table('research_questions').update({'status': 'COMPLETE'}).eq('id', question_id).execute()
                print(f"  -> SUCCESS: Processed question {question_id}.")
            else:
                self.supabase.table('research_questions').update({'status': 'RESEARCH_FAILED'}).eq('id', question_id).execute()
                print(f"  -> FAILED: Could not find evidence for question {question_id}.")

# ==============================================================================
# --- (Define ScoringAgent and NarrativeAgent classes similarly) ---
# You would create these classes following the same pattern.
# ==============================================================================
# ==============================================================================
# --- (This is where you paste the new code) ---
# ==============================================================================

class ScoringAgent(Agent):
    """
    Agent responsible for analyzing evidence and generating an IQSF Index Score Card.
    """
    def _generate_score_card(self, country_name: str, all_evidence: list) -> dict:
        """Uses an LLM to analyze evidence and generate a score card."""
        print("  -> Beginning AI scoring process...")
        print("     (This is a complex analytical task and may take 30-90 seconds)...")

        prompt = f"""
        You are an IQSF Index Analyst. Your task is to generate the official, multi-axis Global Queer Safety Index™ score card for **{country_name}**.

        Your analysis MUST be intersectional. Review the provided evidence and assign separate scores for each identity axis within each dimension where the evidence allows for differentiation. If the data is not specific enough, you may use a single score for that sub-category.

        Your output MUST be a single, valid JSON object.

        **VERIFIED EVIDENCE:**
        {json.dumps(all_evidence, indent=2)}

        **JSON OUTPUT STRUCTURE:**
        {{
          "country": "{country_name}",
          "overall_weighted_score": "[Calculate a single, blended score for headline use]",
          "score_matrix": {{
            "legal_protections": {{
              "overall_score": "[0-100]", "justification": "...",
              "identity_scores": {{ "gay_lesbian": {{ "score": "[0-100]", "notes": "..." }}, "transgender": {{ "score": "[0-100]", "notes": "..." }} }}
            }},
            "physical_safety": {{
              "overall_score": "[0-100]", "justification": "...",
              "identity_scores": {{ "gay_lesbian": {{ "score": "[0-100]", "notes": "..." }}, "transgender": {{ "score": "[0-100]", "notes": "..." }} }}
            }}
          }}
        }}
        """
        try:
            response = self.openai.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": "You are a Senior IQSF Index Analyst. You score countries based on provided evidence and methodology. You only output valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            final_json = response.choices[0].message.content
            print("  -> AI scoring complete.")
            return json.loads(final_json)
        except Exception as e:
            print(f"  -> Error during AI scoring: {e}")
            return None

    def run(self):
        print("-> Searching for completed report to score...")
        response = self.supabase.rpc('get_next_report_for_synthesis').execute()
        report = response.data[0] if response.data else None

        if not report:
            print("-> No reports ready for scoring. All work complete.")
            return

        report_id = report['id']
        country_name = report['country_name']
        print(f"-> Found report ready for scoring: ID {report_id}, Country: {country_name}")
        
        evidence_response = self.supabase.rpc('get_all_evidence_for_report', {'report_id_input': report_id}).execute()
        evidence = evidence_response.data
        
        if not evidence:
            print(f"-> ERROR: Report ID {report_id} is ready, but no evidence was found. Marking as failed.")
            self.supabase.table('reports').update({'status': 'SCORING_FAILED'}).eq('id', report_id).execute()
            return
        
        print(f"  -> Retrieved {len(evidence)} evidence items.")
        score_card = self._generate_score_card(country_name, evidence)

        if score_card:
            self.supabase.table('index_scores').insert({
                'report_id': report_id,
                'country_name': country_name,
                'final_score': score_card.get('overall_weighted_score'),
                'score_data': score_card.get('score_matrix')
            }).execute()
            print(f"  -> Successfully saved Index Score Card for {country_name}.")
            self.supabase.table('reports').update({'status': 'REVIEW'}).eq('id', report_id).execute()
            print(f"-> SUCCESS: Report ID {report_id} is now in 'REVIEW' status.")
        else:
            self.supabase.table('reports').update({'status': 'SCORING_FAILED'}).eq('id', report_id).execute()
            print(f"-> FAILED: Could not generate score card for report {report_id}.")

class NarrativeAgent(Agent):
    """
    Agent responsible for generating a final, human-readable narrative report
    from a scored set of evidence.
    """
    def _generate_narrative(self, country_name: str, score_card: dict, all_evidence: list) -> str:
        """Uses an LLM to write a detailed narrative explaining a country's score."""
        print("  -> Beginning AI narrative generation...")
        print("     (This may take 30-60 seconds)...")

        prompt = f"""
        You are an expert analyst and writer for the International Queer Safety Foundation (IQSF).
        Your task is to write a detailed, 2000-word narrative report for the IQSF Global Queer Safety Index™ on **{country_name}**.

        You have been provided with the final quantitative score card (including intersectional breakdowns) and all the raw evidence.
        Your job is to tell the story BEHIND the numbers. Weave the evidence into a compelling narrative that explains *why* {country_name} received the scores it did, paying special attention to the differences between G/L, Transgender, and other identities.

        **FINAL SCORE CARD:**
        {json.dumps(score_card, indent=2)}
        **RAW EVIDENCE:**
        {json.dumps(all_evidence, indent=2)}

        The output should be only the final article text in Markdown format.
        """
        try:
            response = self.openai.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": "You are an expert IQSF analyst. You write compelling narratives explaining quantitative scores based on provided evidence."},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"  -> Error during AI narrative generation: {e}")
            return None

    def run(self):
        print("-> Searching for scored report to narrate...")
        response = self.supabase.table('reports').select('id, country_name').eq('status', 'REVIEW').limit(1).single().execute()
        report = response.data

        if not report:
            print("-> No reports ready for narrative generation. All work complete.")
            return

        report_id = report['id']
        country_name = report['country_name']
        print(f"-> Found report to narrate: ID {report_id}, Country: {country_name}")

        evidence_response = self.supabase.rpc('get_all_evidence_for_report', {'report_id_input': report_id}).execute()
        score_card_response = self.supabase.table('index_scores').select('*').eq('report_id', report_id).single().execute()
        
        evidence = evidence_response.data
        score_card = score_card_response.data

        if evidence and score_card:
            narrative = self._generate_narrative(country_name, score_card, evidence)
            if narrative:
                # Save or update the narrative in the published_content table
                self.supabase.table('published_content').upsert({'report_id': report_id, 'final_article_text': narrative}, on_conflict='report_id').execute()
                print(f"  -> Successfully saved narrative for Report ID {report_id}.")
                self.supabase.table('reports').update({'status': 'COMPLETE'}).eq('id', report_id).execute()
                print(f"-> SUCCESS: Report ID {report_id} is now 'COMPLETE'.")
            else:
                print(f"-> FAILED: Could not generate narrative for report {report_id}.")
        else:
            print("-> ERROR: Could not retrieve evidence or score card for the report.")

# ==============================================================================
# --- 3. MAIN COMMAND-LINE INTERFACE ---
# ==============================================================================
def main():
    """
    Parses command-line arguments and runs the appropriate agent.
    """
    parser = argparse.ArgumentParser(description="IQSF Agent Framework Controller.")
    subparsers = parser.add_subparsers(dest='agent', required=True, help='The agent to run.')

    # Planner Agent arguments
    plan_parser = subparsers.add_parser('plan', help='Run the Planner Agent.')
    plan_parser.add_argument('-c', '--country', type=str, required=True, help='The country to research.')

    # Gatherer Agent arguments
    gather_parser = subparsers.add_parser('gather', help='Run the Gatherer Agent continuously.')

    # Scorer Agent arguments
    score_parser = subparsers.add_parser('score', help='Run the Scoring Agent.')

    # Narrative Agent arguments
    narrate_parser = subparsers.add_parser('narrate', help='Run the Narrative Agent.')

    args = parser.parse_args()

    # --- Agent Factory ---
    if args.agent == 'plan':
        agent = PlannerAgent()
        agent.run(country=args.country)
    elif args.agent == 'gather':
        agent = GathererAgent()
        agent.run()
    elif args.agent == 'score':
        agent = ScoringAgent()
        agent.run()
    elif args.agent == 'narrate':
        agent = NarrativeAgent()
        agent.run()
    else:
        print(f"Error: Unknown agent '{args.agent}'")

if __name__ == "__main__":
    main()
