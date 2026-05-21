FROM --platform=linux/amd64 amazon/aws-lambda-nodejs:18
WORKDIR ${LAMBDA_TASK_ROOT}

COPY package.json ./
RUN npm install --only=production
COPY index.mjs ./

CMD [ "index.handler" ]
