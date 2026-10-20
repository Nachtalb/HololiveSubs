FROM rust:1.99-alpine AS chef
RUN apk add --no-cache musl-dev && cargo install cargo-chef --locked --version 0.1.78
WORKDIR /src

FROM chef AS plan
COPY Cargo.toml Cargo.lock ./
COPY src src
RUN cargo chef prepare --recipe-path recipe.json

FROM chef AS build
COPY --from=plan /src/recipe.json .
RUN cargo chef cook --release --locked --recipe-path recipe.json
COPY Cargo.toml Cargo.lock ./
COPY src src
RUN cargo build --release --locked && mkdir -p /out/data

FROM scratch
COPY --from=build /src/target/release/holozone /holozone
COPY --from=build --chown=65534:65534 /out/data /data
COPY talents.json /talents.json
COPY www /www
ENV WWW_DIR=/www DATA_DIR=/data TALENTS=/talents.json PORT=8080
USER 65534:65534
EXPOSE 8080
ENTRYPOINT ["/holozone"]
