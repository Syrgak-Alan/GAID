import os
print(os.getcwd())  # should end with .../your_project

# In test_script.ipynb — run from your project root
from gAIde.story_teller.generate_story_func import generate_story_sync
from gAIde.story_teller.config import PLACE, USER_PROFILE
from gAIde.info_image_agent.multi_tool_agent.agent import recognize_showplace_auto



# place = recognize_showplace_auto("image.png", radius_m=150, locale="en")
# print("PLACE:")
# print(place)
story = generate_story_sync("image.png", USER_PROFILE)  # <-- await!
print(story)
