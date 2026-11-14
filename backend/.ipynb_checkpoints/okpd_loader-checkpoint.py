

import csv
import hashlib
import io
import logging
import os
import re


log = logging.getLogger("okpd_loader")


KEY_NAMES = "okpd2:names"
KEY_SECTIONS = "okpd2:sections"
KEY_VERSION = "okpd2:version"


TMP_NAMES = "okpd2:names:tmp"
TMP_SECTIONS = "okpd2:sections:tmp"


BATCH_SIZE = 5000


OKPD_PATTERN = re.compile(
    r"^\d{2}\.\d{2}(\.\d{2,3})?"
)



def decode_csv(raw: bytes) -> str:
    """
    Поддержка UTF-8 и CP1251
    """

    for enc in ("utf-8-sig", "cp1251", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue

    raise ValueError("Не удалось определить кодировку CSV")


def parse_csv(raw: bytes) -> dict[str, str]:
    """
    Парсинг ОКПД2 CSV

    Формат:
        код ; название
    """

    text = decode_csv(raw)

    result = {}

    reader = csv.reader(
        io.StringIO(text),
        delimiter=";"
    )


    for row in reader:

        if len(row) < 2:
            continue


        code = row[0].strip()
        name = row[1].strip()


        if not code or not name:
            continue



        if not OKPD_PATTERN.match(code):
            continue


        result[code] = name


    return result



def read_source(s3) -> bytes | None:
   

    if s3 is None:
        log.error(
            "OKPD: S3 клиент отсутствует"
        )
        return None


    bucket = os.getenv(
        "OKPD_S3_BUCKET",
        "classificators"
    )

    key = os.getenv(
        "OKPD_FILE",
        "okpd.csv"
    )


    try:

        log.info(
            "OKPD: загрузка s3://%s/%s",
            bucket,
            key
        )


        obj = s3.get_object(
            Bucket=bucket,
            Key=key
        )


        body = obj["Body"]


        try:
            raw = body.read()

        finally:
            body.close()


        if len(raw) < 100:

            log.warning(
                "OKPD: файл слишком маленький (%d байт)",
                len(raw)
            )


        log.info(
            "OKPD: получено %d байт",
            len(raw)
        )


        return raw


    except Exception:

        log.exception(
            "OKPD: ошибка загрузки s3://%s/%s",
            bucket,
            key
        )

        return None




def load_okpd(
    r,
    s3,
    force: bool = False
) -> dict:


    raw = read_source(s3)


    if raw is None:

        return {
            "status": "no_source"
        }



    version = hashlib.sha256(
        raw
    ).hexdigest()[:16]




    if (
        not force
        and r.get(KEY_VERSION) == version
        and r.exists(KEY_NAMES)
    ):

        count = r.hlen(KEY_NAMES)


        log.info(
            "OKPD: актуальная версия %s (%d кодов)",
            version,
            count
        )


        return {

            "status": "up_to_date",
            "version": version,
            "codes": count

        }




    names = parse_csv(raw)


    if not names:

        log.error(
            "OKPD: CSV не содержит кодов"
        )

        return {

            "status": "empty"

        }



    log.info(
        "OKPD: найдено %d кодов",
        len(names)
    )





    r.delete(
        TMP_NAMES,
        TMP_SECTIONS
    )


    items = list(
        names.items()
    )



    for i in range(
        0,
        len(items),
        BATCH_SIZE
    ):

        batch = dict(
            items[
                i:i+BATCH_SIZE
            ]
        )


        r.hset(
            TMP_NAMES,
            mapping=batch
        )




    sections = {
        code[:2]
        for code in names.keys()
    }


    if sections:

        r.sadd(
            TMP_SECTIONS,
            *sections
        )



    pipe = r.pipeline(
        transaction=True
    )


    pipe.delete(
        KEY_NAMES,
        KEY_SECTIONS
    )


    pipe.rename(
        TMP_NAMES,
        KEY_NAMES
    )


    pipe.rename(
        TMP_SECTIONS,
        KEY_SECTIONS
    )


    pipe.set(
        KEY_VERSION,
        version
    )


    pipe.execute()



    log.info(
        "OKPD: успешно загружено %d кодов, версия %s",
        len(names),
        version
    )



    return {

        "status": "loaded",
        "version": version,
        "codes": len(names)

    }