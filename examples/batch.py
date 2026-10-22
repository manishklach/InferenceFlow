import os
from packages.python_sdk import InferenceFlowClient
with InferenceFlowClient(os.environ['INFERENCEFLOW_API_KEY']) as client:
    print(client.get_models())
    job=client.create_job([{'custom_id':f'doc-{i:03}','messages':[{'role':'user','content':f'Summarize document {i}'}],'max_output_tokens':128} for i in range(100)])
    print(client.wait_for_job(job['id']))
    print(client.get_results(job['id']))
    print(client.get_wallet())
