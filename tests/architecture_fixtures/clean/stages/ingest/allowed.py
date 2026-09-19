import json

import pandas as pd

from contracts import ProfileContract
from shared.ai_client import AIClient
from stages.ingest import profiling
from stages.ingest.transforms import apply
from . import cleaning
from .ai_plan import build_plan
