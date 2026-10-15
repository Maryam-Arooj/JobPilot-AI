from .profile_agent import ProfileAgent

class CareerOrchestrator:
    def __init__(self):
        self.profile_agent = ProfileAgent()

    def run_profile_extraction(self, text: str):
        return self.profile_agent.extract_from_text(text)
