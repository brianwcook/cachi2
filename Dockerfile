FROM docker.io/library/rockylinux:9 as rockylinux
FROM registry.access.redhat.com/ubi9/ubi as ubi
FROM docker.io/library/golang:1.20.0-bullseye as golang_120
FROM docker.io/library/golang:1.21.0-bullseye as golang_121
FROM docker.io/library/node:22.3.0-bullseye as node_223

########################
# PREPARE OUR BASE IMAGE
########################

FROM ubi as base
COPY --from=rockylinux /etc/yum.repos.d/rocky.repo /etc/yum.repos.d/
COPY --from=rockylinux /etc/pki/rpm-gpg/RPM-GPG-KEY-Rocky-9 /etc/pki/rpm-gpg/
RUN sed -i 's|enabled=1|enabled=0|g' /etc/yum.repos.d/rocky.repo
RUN sed -i 's|$rltype||g' /etc/yum.repos.d/rocky.repo
RUN dnf -y install \
    --setopt install_weak_deps=0 \
    --nodocs \
    git-core \
    python3 \ 
    libffi-devel \
    subscription-manager && \
    dnf clean all

RUN dnf install --enablerepo=appstream -y createrepo_c

# run another one 
######################
# BUILD/INSTALL CACHI2
######################
FROM base as builder
WORKDIR /src
COPY . .
RUN dnf -y install \
    --setopt install_weak_deps=0 \
    --nodocs \
    gcc \
    python3-devel \
    python3-pip \
    python3-setuptools \
    && dnf clean all && \
    python3 --version

RUN python3 -m venv /venv && \
    # todo: add back --require-hashes --no-deps when the pip-compile issue is fixed
    /venv/bin/pip install --upgrade pip && \
    /venv/bin/pip install multidict aiosignal typing_extensions attrs yarl async_timeout idna_ssl --no-cache-dir  && \
    /venv/bin/pip install -r requirements.txt --no-cache-dir  && \
    /venv/bin/pip install --no-cache-dir .

##########################
# ASSEMBLE THE FINAL IMAGE
##########################
FROM base
LABEL maintainer="Red Hat"

# copy Go SDKs and Node.js installation from official images
COPY --from=golang_120 /usr/local/go /usr/local/go/go1.20
COPY --from=golang_121 /usr/local/go /usr/local/go/go1.21
COPY --from=node_223 /usr/local/lib/node_modules/corepack /usr/local/lib/corepack
COPY --from=node_223 /usr/local/bin/node /usr/local/bin/node
COPY --from=builder /venv /venv

# link corepack, yarn, and go to standard PATH location
RUN ln -s /usr/local/lib/corepack/dist/corepack.js /usr/local/bin/corepack && \
    ln -s /usr/local/lib/corepack/dist/yarn.js /usr/local/bin/yarn && \
    ln -s /usr/local/go/go1.21/bin/go /usr/local/bin/go && \
    ln -s /venv/bin/cachi2 /usr/local/bin/cachi2

ENTRYPOINT ["/usr/local/bin/cachi2"]
