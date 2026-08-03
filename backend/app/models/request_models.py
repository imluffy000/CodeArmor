from pydantic import BaseModel

class ReviewRequest(BaseModel):

    pr_url: str