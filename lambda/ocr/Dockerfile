FROM public.ecr.aws/lambda/python:3.12

# OpenCV's wheel needs these shared libraries on AL2023.
RUN dnf install -y mesa-libGL glib2 libgomp && dnf clean all
COPY requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt
COPY errors.py extraction.py ocr_engine.py handler.py ${LAMBDA_TASK_ROOT}/
# Fail the build if the models or native libraries cannot be initialized.
RUN python -c "from ocr_engine import _rapid_engine; _rapid_engine()"
CMD ["handler.lambda_handler"]
