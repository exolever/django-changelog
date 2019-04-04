FROM themattrix/tox-base

LABEL maintainer="OpenExO <devops@openexo.com>"

RUN apt-get update && apt-get install -y --no-install-recommends libgraphviz-dev

COPY . .

ARG SKIP_TOX=false
RUN bash -c " \
    if [ -f 'install-prereqs.sh' ]; then \
        bash install-prereqs.sh; \
    fi && \
    if [ $SKIP_TOX == false ]; then \
        TOXBUILD=true tox; \
    fi"
