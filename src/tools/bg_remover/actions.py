from loguru import logger
from pathlib import Path
from typing import Union
from rembg import remove


from src.schemas.common import ImageFormat
from src.utils.common import save_image, read_image


class BackgroundRemovalError(Exception):
    pass


class BackgroundRemover:
    def __init__(self, output_format: ImageFormat = ImageFormat.PNG):
        self.output_format = output_format

    def remove_background(
        self, input_path: Union[str, Path], output_path: Union[str, Path]
    ) -> Path:
        """
        Removes the background of the image at input_path and saves it to output_path.
        """
        try:
            logger.info(f"Reading image: {input_path}")
            img = read_image(input_path)

            logger.info("Removing background...")
            output_img = remove(img)

            logger.info(f"Saving image to: {output_path}")
            final_path = save_image(output_img, output_path, self.output_format)

            logger.info(f"Successfully saved to {final_path}")
            return final_path

        except Exception as e:
            logger.error("Background removal failed", exc_info=True)
            raise BackgroundRemovalError(f"Error processing {input_path}: {e}") from e


if __name__ == "__main__":
    remover = BackgroundRemover(output_format=ImageFormat.PNG)
    try:
        input_file = ""
        output_file = "output/bg_remover/cleaned_image"
        result_path = remover.remove_background(input_file, output_file)
        logger.error(f"Image saved at: {result_path}")
    except Exception as e:
        logger.error(f"Error: {e}")
