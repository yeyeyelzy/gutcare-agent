ARG GO_VERSION=1.24.4
FROM golang:${GO_VERSION}-bookworm AS build
ARG MINIO_SOURCE_COMMIT
RUN test -n "$MINIO_SOURCE_COMMIT" && echo "$MINIO_SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'
RUN git clone https://github.com/minio/minio.git /src && cd /src && git checkout "$MINIO_SOURCE_COMMIT" && test "$(git rev-parse HEAD)" = "$MINIO_SOURCE_COMMIT"
WORKDIR /src
RUN CGO_ENABLED=0 go build -trimpath -ldflags "-s -w -X github.com/minio/minio/cmd.Version=REPRODUCIBLE" -o /out/minio ./
RUN mkdir -p /out/data /out/home && chown -R 65532:65532 /out/data /out/home

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build --chown=nonroot:nonroot /out/minio /usr/bin/minio
COPY --from=build --chown=nonroot:nonroot /out/data /data
COPY --from=build --chown=nonroot:nonroot /out/home /home/nonroot
ENV HOME=/home/nonroot
USER nonroot:nonroot
ENTRYPOINT ["/usr/bin/minio"]
