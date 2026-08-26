import os
import sys

# The package is deployed flat into a cloud function, so its modules import each
# other by bare name. Tests import them the same way.
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "feed_robot")
)
