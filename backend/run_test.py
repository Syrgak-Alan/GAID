import os
print(os.getcwd())  # should end with .../your_project

# In test_script.ipynb — run from your project root
from gAIde.story_teller.generate_story_func import generate_story_sync
from gAIde.config import PLACE, USER_PROFILE

story = generate_story_sync(PLACE, USER_PROFILE)  # <-- await!
print(story)
